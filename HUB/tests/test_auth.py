"""Volunteer login, access, rotation and power rule (hub/auth.py, hub/rotation.py)."""
import pytest
from fastapi.testclient import TestClient

from hub import auth, rotation
from hub.app import CAT, app
from hub.rotation import CLOCK, POWER

GUIDELINE = "P21"                       # Clinical Guideline Chapter, group medical
FINANCIAL = next(d["doc_id"] for d in CAT.docs.values()
                 if d["genre"] == "Financial Report" and not d["is_junk"] and not d["duplicate_of"])


@pytest.fixture
def pins():
    """Fresh demo accounts, real clock, mains power, empty rate limiter for every test."""
    CLOCK.reset()
    POWER.set_status("mains")
    rotation._reveal.clear()
    return auth.seed_demo(auth.store())


@pytest.fixture
def client():
    return TestClient(app)     # no `with`: the 60 s scheduler thread is not started in tests


def login(client, username, pin, scope="volunteer"):
    return client.post("/auth/login", json={"username": username, "pin": pin, "scope": scope})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def admin_token(client, pins):
    r = login(client, "admin_sara", pins["admin_sara"], scope="admin")
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_login_ok(client, pins):
    r = login(client, "dr_amina", pins["dr_amina"])
    assert r.status_code == 200
    tok = r.json()["token"]
    me = client.get("/auth/me", headers=bearer(tok)).json()["volunteer"]
    assert me["grp"] == "medical" and me["status"] == "active"
    assert client.get(f"/docs/{GUIDELINE}/text", headers=bearer(tok)).status_code == 200
    assert pins["dr_amina"] not in str(auth.store().q("SELECT * FROM auth_log"))   # PIN never logged


def test_wrong_pin_generic_error(client, pins):
    wrong = "000000" if pins["dr_amina"] != "000000" else "111111"
    r = login(client, "dr_amina", wrong)
    assert r.status_code == 401 and r.json()["detail"] == auth.GENERIC_ERROR
    r = login(client, "nobody_here", wrong)
    assert r.status_code == 401 and r.json()["detail"] == auth.GENERIC_ERROR


def test_rate_limit(client, pins):
    for _ in range(auth.RATE_LIMIT):
        assert login(client, "comms_lea", "999999x").status_code == 401
    assert login(client, "comms_lea", pins["comms_lea"]).status_code == 429


def test_inactive_refused(client, pins):
    adm = admin_token(client, pins)
    assert client.post("/admin/volunteers/vol-karim/deactivate", headers=bearer(adm)).status_code == 200
    r = login(client, "log_karim", pins["log_karim"])
    assert r.status_code == 401 and r.json()["detail"] == auth.GENERIC_ERROR


def test_expired_mission_refused(client, pins):
    r = login(client, "old_tom", pins["old_tom"])
    assert r.status_code == 401 and r.json()["detail"] == auth.GENERIC_ERROR
    assert auth.store().one("SELECT status FROM volunteers WHERE volunteer_id = 'vol-tom'")["status"] == "expired"


def test_direct_doc_url_needs_token(client, pins):
    assert client.get(f"/docs/{GUIDELINE}/text").status_code == 401
    assert client.get(f"/docs/{GUIDELINE}/original").status_code == 401
    assert client.post("/search", json={"q": "tuberculosis"}).status_code == 401
    assert client.post("/requests", json={"doc_id": GUIDELINE}).status_code == 401
    assert client.get(f"/docs/{GUIDELINE}/text", headers=bearer("forged-token")).status_code == 401


def test_out_of_group_restricted_doc_refused(client, pins):
    tok = login(client, "comms_lea", pins["comms_lea"]).json()["token"]
    assert client.get(f"/docs/{FINANCIAL}/text", headers=bearer(tok)).status_code == 403
    r = client.post("/search", json={"q": "financial report", "role": "admin"}, headers=bearer(tok)).json()
    fin = [x for x in r["results"] if x["doc_id"] == FINANCIAL]
    assert not fin or fin[0]["access"] == "needs_approval"     # client-sent role is ignored
    # existing approval flow still works for volunteers
    req = client.post("/requests", json={"doc_id": FINANCIAL, "want": "access"}, headers=bearer(tok)).json()
    assert req["status"] == "AWAITING_APPROVAL"
    client.post(f"/requests/{req['id']}/approve")
    assert client.get(f"/docs/{FINANCIAL}/text", headers=bearer(tok)).status_code == 200


def _rotate_and_deliver(client, adm, vid):
    shown = client.post(f"/admin/volunteers/{vid}/reveal", headers=bearer(adm))
    assert shown.status_code == 200
    again = client.post(f"/admin/volunteers/{vid}/reveal", headers=bearer(adm))
    assert again.status_code == 404                              # shown only once
    secret = shown.json()
    assert client.post(f"/admin/volunteers/{vid}/confirm", headers=bearer(adm)).status_code == 200
    return secret


def test_rotation_with_mains(client, pins):
    adm = admin_token(client, pins)
    r = client.post("/admin/clock", json={"days": 7}, headers=bearer(adm)).json()
    assert "vol-amina" in r["scheduler"]["rotated"]
    # until delivery is confirmed the old credential still works
    assert login(client, "dr_amina", pins["dr_amina"]).status_code == 200
    secret = _rotate_and_deliver(client, adm, "vol-amina")
    assert login(client, "dr_amina", pins["dr_amina"]).status_code == 401
    assert login(client, secret["username"], secret["pin"]).status_code == 200
    assert pins["dr_amina"] not in str(auth.store().q("SELECT * FROM auth_log"))


def test_rotation_pending_during_outage_then_mains(client, pins):
    adm = admin_token(client, pins)
    client.post("/admin/power", json={"status": "outage"}, headers=bearer(adm))
    r = client.post("/admin/clock", json={"days": 7}, headers=bearer(adm)).json()
    assert "vol-amina" in r["scheduler"]["pending"] and not r["scheduler"]["rotated"]
    vol = auth.store().one("SELECT rotation_pending FROM volunteers WHERE volunteer_id = 'vol-amina'")
    assert vol["rotation_pending"] == 1
    assert login(client, "dr_amina", pins["dr_amina"]).status_code == 200   # old credential still valid
    r = client.post("/admin/power", json={"status": "mains"}, headers=bearer(adm)).json()
    assert "vol-amina" in r["scheduler"]["rotated"]
    vol = auth.store().one("SELECT rotation_pending FROM volunteers WHERE volunteer_id = 'vol-amina'")
    assert vol["rotation_pending"] == 0
    secret = _rotate_and_deliver(client, adm, "vol-amina")
    assert login(client, secret["username"], secret["pin"]).status_code == 200


def test_mission_expiring_during_outage_blocks_login(client, pins):
    adm = admin_token(client, pins)
    client.post("/admin/power", json={"status": "outage"}, headers=bearer(adm))
    client.post("/admin/clock", json={"days": 7}, headers=bearer(adm))      # rotation pending
    client.post("/admin/clock", json={"days": 200}, headers=bearer(adm))    # past Amina's mission end
    r = login(client, "dr_amina", pins["dr_amina"])
    assert r.status_code == 401 and r.json()["detail"] == auth.GENERIC_ERROR
    assert auth.store().one("SELECT status FROM volunteers WHERE volunteer_id = 'vol-amina'")["status"] == "expired"


def test_deactivation_kills_existing_session(client, pins):
    tok = login(client, "log_karim", pins["log_karim"]).json()["token"]
    assert client.post("/search", json={"q": "cholera"}, headers=bearer(tok)).status_code == 200
    adm = admin_token(client, pins)
    client.post("/admin/volunteers/vol-karim/deactivate", headers=bearer(adm))
    r = client.post("/search", json={"q": "cholera"}, headers=bearer(tok))
    assert r.status_code == 401 and r.json()["detail"] == auth.ENDED_MESSAGE


def test_admin_endpoints_need_admin(client, pins):
    tok = login(client, "dr_amina", pins["dr_amina"]).json()["token"]
    assert client.get("/admin/volunteers", headers=bearer(tok)).status_code == 403
    assert client.get("/admin/volunteers").status_code == 401
    assert login(client, "dr_amina", pins["dr_amina"], scope="admin").status_code == 401


def test_existing_open_endpoints_still_work(client, pins):
    assert client.get("/status").status_code == 200
    assert client.post("/admin/budget", json={"budget_mb": 50}).json()["budget_mb"] == 50
    assert client.post("/admin/budget", json={"budget_mb": 150}).status_code == 200
    assert client.get("/").status_code == 200 and client.get("/login").status_code == 200
