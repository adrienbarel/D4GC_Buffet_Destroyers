"""Mission hub: one FastAPI process for the demo (PROJECT_SPEC 8, 10, 9 simplified).

Run:  python run_all.py      (or: uvicorn hub.app:app --host 127.0.0.1 --port 8000)
Open: http://127.0.0.1:8000

Simplifications for the proof of concept (say them in the pitch):
- Devices are simulated by a "role / device" selector instead of 4 separate processes.
- Cloud downloads and the LoRa relay are simulated in-process (accelerated clock).
- Original PDFs/HTML are not in this workspace: sizes come from originals_manifest.csv.
- No user login yet: the role is chosen in the UI. Bind to 127.0.0.1 only.
"""
from __future__ import annotations

import hashlib
import itertools
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from common import lora_codec
from common.config import load
from common.log import get_logger
from common.search import Catalog
from hub import access as access_rules
from hub import auth, rotation
from hub.auth import current_volunteer
from hub.planner import compute_plan

log = get_logger("hub")
CFG = load()
CATALOG_PATH: Path = CFG["paths"]["catalog_db"]
if not CATALOG_PATH.exists():
    raise SystemExit(f"{CATALOG_PATH} not found: run  python preprocess/build_catalog.py  first")
CAT = Catalog(CATALOG_PATH, CFG)
STATIC = Path(__file__).with_name("static")

# role/device -> staff group (the 4 simulated devices of config.yaml)
ROLES = {
    "doctor": {"label": "Doctor (medical-1)", "group": "medical"},
    "fieldops": {"label": "Field ops / logistics (fieldops-1)", "group": "field_ops"},
    "comms": {"label": "Communications (comms-1)", "group": "communications"},
    "admin": {"label": "Admin / legal (admin-1)", "group": "admin_legal"},
}
GROUP_ROLE = {v["group"]: k for k, v in ROLES.items()}   # volunteer grp -> device role key


def role_for(vol: dict) -> str:
    """The access identity of a signed-in volunteer = their group (never a client-sent field)."""
    return GROUP_ROLE[vol["grp"]]


def who(vol: dict) -> str:
    return f"{vol['full_name']} ({vol['grp']})"


EMERGENCY_GENRES = {"medical": {"Clinical Guideline Chapter"}}   # no protocol genres exist for other groups
NO_VERIFIED = ("No sufficiently verified procedure found. Consult the authorized mission protocol "
               "or designated responsible officer.")
DEMO_SPEED_MBPS = {"internet": 2.0, "satellite": 0.4}   # accelerated so the demo is watchable
NODES = {"A": 1, "R1": 101, "R2": 102, "R3": 103, "B": 2, "C": 3}


def now_s() -> str:
    return datetime.now().strftime("%H:%M:%S")


class State:
    """All mutable hub state (in memory for the demo)."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.internet = True
        self.relay = True
        self.hub_c_internet = False
        self.budget_mb = float(CFG["hub"]["budget_mb"])
        self.views: list[tuple[str, float]] = []
        self.fetched: set[str] = set()
        self.approved: set[tuple[str, str]] = set()          # (role, doc_id)
        self.requests: dict[int, dict] = {}
        self.access_log: list[dict] = []
        self.relay_log: list[dict] = []
        self.req_ids = itertools.count(1)
        self.msg_ids = itertools.count(1)
        self.always_mb = CATALOG_PATH.stat().st_size / 1e6
        self.docs = [d for d in CAT.docs.values() if not d["is_junk"] and not d["duplicate_of"]]
        self.plan: dict = {}
        self.replan("startup")

    def replan(self, why: str) -> None:
        self.plan = compute_plan(self.docs, CFG, self.budget_mb, self.always_mb, self.views)
        s = self.plan["summary"]
        log.info("re-plan (%s): budget %.0f MB -> core %s MB, reserve %s MB, tiers %s",
                 why, self.budget_mb, s["core_mb"], s["reserve_mb"], s["docs_per_tier"])

    def availability(self, doc_id: str) -> str:
        tier = self.plan["tiers"].get(doc_id, "text_only")
        if tier in ("core", "reserve"):
            return f"original_on_hub ({tier})"
        if doc_id in self.fetched:
            return "original_on_hub (fetched)"
        return "text_on_hub_original_in_cloud"

    def access(self, role: str, doc: dict) -> str:
        """'allowed' | 'log' | 'needs_approval' (rules in hub/access.py)."""
        return access_rules.decide(ROLES[role]["group"], doc, (role, doc["doc_id"]) in self.approved, CFG)

    def log_access(self, role: str, doc_id: str, action: str, allowed: bool, reason: str,
                   who: str | None = None) -> None:
        self.access_log.insert(0, {"ts": now_s(), "device": who or ROLES[role]["label"], "doc_id": doc_id,
                                   "title": CAT.docs[doc_id]["title"], "action": action,
                                   "allowed": allowed, "reason": reason})
        log.info("access %s %s %s allowed=%s (%s)", role, action, doc_id, allowed, reason)


S = State()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup: open/seed the volunteer DB, run one rotation pass, then one pass every 60 s."""
    auth.store()
    rotation.run_scheduler()
    rotation.start_scheduler()
    yield


app = FastAPI(title="MSF Field Knowledge Hub (demo)", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.include_router(auth.router)

_PROXY_PREFIX = re.compile(r"^/(?:abs)?proxy/\d+(?=/|$)")


@app.middleware("http")
async def strip_proxy_prefix(request, call_next):
    """Accept requests forwarded with an IDE port-forwarding prefix (/proxy/8000/..., /absproxy/8000/...)."""
    path = request.scope["path"]
    stripped = _PROXY_PREFIX.sub("", path)
    if stripped != path:
        request.scope["path"] = stripped or "/"
    return await call_next(request)


def get_doc(doc_id: str) -> dict:
    doc = CAT.docs.get(doc_id)
    if not doc or doc["is_junk"]:
        raise HTTPException(404, "unknown document")
    return doc


def check_role(role: str) -> None:
    if role not in ROLES:
        raise HTTPException(400, f"role must be one of {list(ROLES)}")


# --------------------------------------------------------------------------- pages + status
@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/login")
def login_page() -> FileResponse:
    return FileResponse(STATIC / "login.html")


@app.get("/status")
def status() -> dict[str, Any]:
    with S.lock:
        _tick_requests()
        return {"internet": S.internet, "relay": S.relay, "hub_c_internet": S.hub_c_internet,
                "budget_mb": S.budget_mb, "plan": S.plan["summary"], "docs_indexed": CAT.n_searchable,
                "mission": CFG["mission"]["name"], "roles": ROLES,
                "pending_requests": sum(1 for r in S.requests.values() if r["status"] not in ("DELIVERED", "REJECTED", "APPROVED")),
                "fetched_originals": len(S.fetched)}


class Connectivity(BaseModel):
    internet: bool | None = None
    relay: bool | None = None
    hub_c_internet: bool | None = None


@app.post("/admin/connectivity")
def connectivity(body: Connectivity) -> dict:
    with S.lock:
        for key in ("internet", "relay", "hub_c_internet"):
            value = getattr(body, key)
            if value is not None and value != getattr(S, key):
                setattr(S, key, value)
                log.info("connectivity: %s -> %s", key, "ON" if value else "OFF")
        if S.internet:  # queued requests start as soon as internet is back
            for req in S.requests.values():
                if req["status"] == "QUEUED":
                    _start_download(req, "internet")
        return status()


class Budget(BaseModel):
    budget_mb: float


@app.post("/admin/budget")
def set_budget(body: Budget) -> dict:
    with S.lock:
        S.budget_mb = max(20.0, min(450.0, body.budget_mb))
        S.replan(f"slider {S.budget_mb:.0f} MB")
        return S.plan["summary"]


@app.get("/admin/plan")
def get_plan(tier: str | None = None, q: str = "", limit: int = 200) -> dict:
    with S.lock:
        rows = S.plan["rows"]
        if tier:
            rows = [r for r in rows if r["tier"] == tier]
        if q:
            rows = [r for r in rows if q.lower() in (r["title"] or "").lower() or q.lower() in r["genre"].lower()]
        return {"summary": S.plan["summary"], "rows": rows[:limit], "total": len(rows)}


# --------------------------------------------------------------------------- search + documents
class SearchBody(BaseModel):
    q: str
    role: str = "doctor"
    lang_mode: str = "auto"          # auto | only | all
    lang: str | None = None          # manual language override
    k: int = 10


def _decorate(result: dict, role: str) -> dict:
    doc = CAT.docs[result["doc_id"]]
    result["availability"] = S.availability(doc["doc_id"])
    result["access"] = S.access(role, doc)
    if result["access"] == "needs_approval":   # never leak restricted content in snippets
        result["snippet"] = "🔒 Restricted outside its group: request approval to read."
    return result


@app.post("/search")
def search(body: SearchBody, vol: dict = Depends(current_volunteer)) -> dict:
    role = role_for(vol)                      # body.role is ignored: identity comes from the session
    started = time.perf_counter()
    res = CAT.search(body.q, group=ROLES[role]["group"], k=body.k,
                     lang_mode=body.lang_mode, lang_override=body.lang)
    with S.lock:
        res["results"] = [_decorate(r, role) for r in res["results"]]
        res["maybe"] = [_decorate(r, role) for r in res["maybe"]]
    res["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
    log.info("search %s q=%r -> %d results in %.0f ms", vol["volunteer_id"], body.q, len(res["results"]), res["latency_ms"])
    return res


@app.post("/emergency")
def emergency(body: SearchBody, vol: dict = Depends(current_volunteer)) -> dict:
    """Extractive only: exact source passage + citation, never generated instructions."""
    role = role_for(vol)
    group = ROLES[role]["group"]
    genres = EMERGENCY_GENRES.get(group)
    res = CAT.search(body.q, group=group, k=5, lang_mode="auto", genres=genres) if genres else {"results": [], "language": None}
    with S.lock:  # low-confidence candidates are still shown, clearly labelled UNVERIFIED
        cands = [_decorate(r, role) for r in (res["results"] or res.get("maybe", []))]
    cands = [c for c in cands if c["access"] != "needs_approval"]
    card = None
    if cands:
        top = cands[0]
        chunk = CAT.chunk(top["chunk_id"])
        card = {**top, "excerpt": chunk.get("text", ""), "citation": {
            "doc_id": top["doc_id"], "file": f"{top['doc_id']}.{top['original_ext']}",
            "section": chunk.get("heading") or "(no section heading)", "chunk": chunk.get("ord"),
            "page": "unknown (PDF page mapping not available)"},
            "validation": "NOT VERIFIED: genre comes from the CSV; no MSF validation record exists"}
    return {"query": body.q, "role": role, "group": group, "language": res.get("language"),
            "verified_procedure_found": False, "message": NO_VERIFIED,
            "closest_unverified_source": card,
            "note": None if genres else f"No protocol-type documents exist for group '{group}' in this corpus."}


def _check_open(vol: dict, doc: dict, action: str) -> str:
    """Access check for opening a document as a volunteer; logs to access_log and auth_log."""
    role = role_for(vol)
    with S.lock:
        access = S.access(role, doc)
        if access == "needs_approval":
            S.log_access(role, doc["doc_id"], action, False, "restricted genre outside group", who(vol))
            auth.auth_event(vol["volunteer_id"], "doc_open", False, f"{doc['doc_id']} needs approval")
            raise HTTPException(403, "needs_approval")
        S.log_access(role, doc["doc_id"], action, True,
                     "own group" if access == "allowed" else "outside group (logged)", who(vol))
        S.views.append((doc["doc_id"], time.time()))
    auth.auth_event(vol["volunteer_id"], "doc_open", True, f"{doc['doc_id']} ({action})")
    return access


@app.get("/docs/{doc_id}/text", response_class=PlainTextResponse)
def doc_text(doc_id: str, vol: dict = Depends(current_volunteer)) -> str:
    doc = get_doc(doc_id)
    _check_open(vol, doc, "open_text")
    return CAT.text(doc_id)


@app.get("/docs/{doc_id}/original")
def doc_original(doc_id: str, vol: dict = Depends(current_volunteer)):
    """The original file after the access check. 404 + fetchable when the hub does not hold it."""
    doc = get_doc(doc_id)
    with S.lock:
        on_hub = S.availability(doc_id).startswith("original_on_hub")
    if not on_hub:
        return JSONResponse({"detail": "original not on hub", "fetchable": True}, status_code=404)
    _check_open(vol, doc, "open_original")
    real = CFG["paths"]["cloud_store"] / "original" / f"{doc_id}.{doc['original_ext']}"
    if real.exists():
        return FileResponse(real)
    size = (doc["original_bytes"] or 0) / 1e6
    return HTMLResponse(f"<!doctype html><meta charset='utf-8'><title>{doc_id}</title>"
                        f"<p>Original of <b>{doc_id}</b> ({doc['original_ext']}, {size:.2f} MB) is on the hub. "
                        "The real PDF/HTML files are not included in this workspace (sizes come from "
                        "originals_manifest.csv).</p>")


# --------------------------------------------------------------------------- requests (cloud + relay)
class RequestBody(BaseModel):
    doc_id: str
    role: str = "doctor"
    want: str = "original"           # original | access


class Choice(BaseModel):
    path: str                        # wait_internet | satellite | courier


def _req_log(req: dict, msg: str) -> None:
    req["log"].append({"ts": now_s(), "msg": msg})
    req["updated_at"] = now_s()
    log.info("request #%d %s: %s", req["id"], req["doc_id"], msg)


def _start_download(req: dict, link: str) -> None:
    req.update(status="DOWNLOADING", path=link, started=time.time(), progress=0.0)
    _req_log(req, f"downloading {req['size_mb']:.2f} MB via {link}")


def _tick_requests() -> None:
    """Advance simulated downloads (accelerated clock)."""
    for req in S.requests.values():
        if req["status"] != "DOWNLOADING":
            continue
        speed = DEMO_SPEED_MBPS[req["path"]]
        req["progress"] = min(1.0, (time.time() - req["started"]) * speed / max(req["size_mb"], 0.01))
        if req["progress"] >= 1.0:
            req["status"] = "DELIVERED"
            S.fetched.add(req["doc_id"])
            _req_log(req, "original stored on hub, delivered to device")


def _hub_b_has(doc_id: str) -> bool:
    """Neighbour hub B caches a deterministic ~40% of originals."""
    return hashlib.sha256(f"B:{doc_id}".encode()).digest()[0] < 102


def _relay_query(req: dict) -> dict:
    """Flood WHO_HAS A->R1->R2->(B, R3->C) with TTL 3; collect I_HAVE answers."""
    doc_id, msg_id = req["doc_id"], next(S.msg_ids) % 65535
    size_kb = int(req["size_mb"] * 1000)
    hops, t = [], 0
    who = lora_codec.pack_who_has(NODES["A"], msg_id, 3, doc_id, True)
    for src, dst in (("A", "R1"), ("R1", "R2"), ("R2", "B"), ("R2", "R3"), ("R3", "C")):
        t += CFG["links"]["relay"]["hop_delay_s"]
        hops.append((t, src, dst, "WHO_HAS", who))
    b_has, c_inet = _hub_b_has(doc_id), S.hub_c_internet
    if b_has:
        ans = lora_codec.pack_i_have(NODES["B"], msg_id, True, True, False, size_kb)
        for src, dst in (("B", "R2"), ("R2", "R1"), ("R1", "A")):
            t += 2
            hops.append((t, src, dst, "I_HAVE", ans))
    if c_inet:
        ans = lora_codec.pack_i_have(NODES["C"], msg_id, True, False, True, size_kb)
        for src, dst in (("C", "R3"), ("R3", "R2"), ("R2", "R1"), ("R1", "A")):
            t += 2
            hops.append((t, src, dst, "I_HAVE", ans))
    for t_off, src, dst, kind, payload in hops:
        S.relay_log.insert(0, {"ts": now_s(), "t": f"+{t_off}s", "msg_id": msg_id, "src": src, "dst": dst,
                               "type": kind, "bytes": len(payload), "hex": payload.hex(" "), "doc_id": doc_id})
    return {"hub_b_has_original": b_has, "hub_c_has_internet": c_inet, "messages": len(hops),
            "bytes_on_air": sum(len(p) for *_, p in hops)}


def _options(req: dict, relay: dict | None) -> list[dict]:
    links, size = CFG["links"], req["size_mb"]
    urgent = CAT.docs[req["doc_id"]]["genre"] in ("Clinical Guideline Chapter", "Study Protocol")
    opts = [
        {"path": "wait_internet", "eta": "unknown (internet up ~30% of the time)", "eta_s": None, "cost": 0.0},
        {"path": "satellite", "eta": f"{size * links['satellite']['seconds_per_mb']:.0f} s",
         "eta_s": size * links["satellite"]["seconds_per_mb"], "cost": round(size * links["satellite"]["cost_per_mb"], 1)},
        {"path": "courier", "eta": f"{links['courier']['fixed_hours']} h",
         "eta_s": links["courier"]["fixed_hours"] * 3600, "cost": links["courier"]["fixed_cost"],
         "note": "from Hub B (has it, answered over LoRa)" if relay and relay["hub_b_has_original"] else "to regional office"},
    ]
    max_eta = 3600 if urgent else 48 * 3600
    fitting = [o for o in opts if o["eta_s"] is not None and o["eta_s"] <= max_eta]
    best = min(fitting, key=lambda o: o["cost"]) if (urgent and fitting) else opts[0]
    for o in opts:
        o["recommended"] = o is best
    return opts


@app.post("/requests")
def create_request(body: RequestBody, vol: dict = Depends(current_volunteer)) -> dict:
    role = role_for(vol)                      # body.role is ignored: identity comes from the session
    doc = get_doc(body.doc_id)
    with S.lock:
        req = {"id": next(S.req_ids), "doc_id": doc["doc_id"], "title": doc["title"], "role": role,
               "device": who(vol), "want": body.want, "status": "NEW", "path": None,
               "size_mb": round((doc["original_bytes"] or 0) / 1e6, 3), "progress": 0.0, "options": None,
               "relay": None, "log": [], "created_at": now_s(), "updated_at": now_s()}
        S.requests[req["id"]] = req
        _req_log(req, f"new request for {body.want}")
        if body.want == "access":
            req["status"] = "AWAITING_APPROVAL"
            S.log_access(role, doc["doc_id"], "request_access", False, "awaiting hub operator approval", who(vol))
            _req_log(req, "restricted document: waiting for hub operator approval")
        elif S.availability(doc["doc_id"]).startswith("original_on_hub"):
            req["status"] = "DELIVERED"
            _req_log(req, "original already on hub: served over local Wi-Fi")
        elif S.internet:
            _start_download(req, "internet")
        else:
            _req_log(req, "internet OFF: text already readable from hub")
            if S.relay:
                req["status"] = "RELAY_QUERY"
                req["relay"] = _relay_query(req)
                _req_log(req, f"LoRa WHO_HAS sent ({req['relay']['bytes_on_air']} bytes on air in "
                              f"{req['relay']['messages']} hops)")
            req["options"] = _options(req, req["relay"])
            req["status"] = "OPTIONS_READY"
            _req_log(req, "options ready: choose a path")
        return req


@app.get("/requests")
def list_requests() -> list[dict]:
    with S.lock:
        _tick_requests()
        return sorted(S.requests.values(), key=lambda r: -r["id"])


@app.post("/requests/{req_id}/choose")
def choose(req_id: int, body: Choice) -> dict:
    with S.lock:
        req = S.requests.get(req_id) or {}
        if req.get("status") != "OPTIONS_READY":
            raise HTTPException(409, "request is not waiting for a choice")
        if body.path == "wait_internet":
            req["status"] = "QUEUED"
            _req_log(req, "queued: starts automatically when internet returns")
        elif body.path == "satellite":
            _start_download(req, "satellite")
        elif body.path == "courier":
            doc = CAT.docs[req["doc_id"]]
            req["status"] = "COURIER_TICKET"
            req["ticket"] = {"ticket_id": f"T{req_id:04d}", "from_hub": "B" if (req["relay"] or {}).get("hub_b_has_original") else "regional office",
                             "to_hub": "A", "docs": [{"doc_id": doc["doc_id"], "sha256": doc["sha256"], "size_mb": req["size_mb"]}]}
            _req_log(req, f"courier ticket {req['ticket']['ticket_id']} created (SHA-256 checked on return)")
        else:
            raise HTTPException(400, "unknown path")
        return req


@app.post("/requests/{req_id}/{decision}")
def decide(req_id: int, decision: str) -> dict:
    if decision not in ("approve", "reject"):
        raise HTTPException(404)
    with S.lock:
        req = S.requests.get(req_id) or {}
        if req.get("status") != "AWAITING_APPROVAL":
            raise HTTPException(409, "request is not awaiting approval")
        ok = decision == "approve"
        req["status"] = "APPROVED" if ok else "REJECTED"
        if ok:
            S.approved.add((req["role"], req["doc_id"]))
        S.log_access(req["role"], req["doc_id"], decision, ok, "hub operator decision", req["device"])
        _req_log(req, f"hub operator: {decision}")
        return req


@app.get("/relay/log")
def relay_log(limit: int = 60) -> list[dict]:
    with S.lock:
        return S.relay_log[:limit]


@app.get("/access/log")
def access_log(limit: int = 100) -> list[dict]:
    with S.lock:
        return S.access_log[:limit]
