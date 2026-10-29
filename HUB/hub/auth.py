"""Volunteer login, sessions and the admin "Volunteers" API. Python stdlib only.

- PINs: hashlib.scrypt (n=2^14, r=8, p=1) with a random 16-byte salt, compared with hmac.compare_digest.
- Sessions: random token (secrets.token_urlsafe), only its SHA-256 is stored, valid 8 h.
  Browser: HttpOnly + SameSite=Strict cookie. API clients: "Authorization: Bearer <token>".
- current_volunteer() re-checks status + mission_end on EVERY request, so deactivation or
  mission expiry kills existing sessions immediately.
- Login failures always return the same message; 5 failures per username in 5 min -> 429.
- PINs are never logged or stored in clear. Demo PINs are printed ONCE to the console at seed time.

Reset the demo accounts (prints new PINs):  python -m hub.auth --reset-demo
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sys
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from common.config import load
from common.log import get_logger
from hub import db, rotation
from hub.rotation import CLOCK, POWER, iso, parse

log = get_logger("auth")

GENERIC_ERROR = "Invalid credentials or access ended"
ENDED_MESSAGE = "Your mission authorization has ended. Contact an administrator."
GROUPS = ("medical", "field_ops", "communications", "admin_legal")
SESSION_HOURS = 8
RATE_LIMIT, RATE_WINDOW_S = 5, 300
SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
COOKIE = {"volunteer": "pr_session", "admin": "pr_admin"}


def session_now() -> datetime:
    """Session lifetime (8 h) uses REAL time, so the demo "advance clock" button does not log the admin out.
    Mission end, expiry and rotation use the demo clock (CLOCK.now())."""
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- storage
class Store:
    """One SQLite connection + a lock (FastAPI runs sync endpoints in a thread pool)."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.conn = db.connect(path)
        self.conn.isolation_level = None          # autocommit; explicit transactions via tx()
        db.init_hub(self.conn)

    def q(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple = ()) -> dict | None:
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def x(self, sql: str, args: tuple = ()) -> None:
        with self.lock:
            self.conn.execute(sql, args)

    @contextmanager
    def tx(self):
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise


_STORE: Store | None = None
_STORE_LOCK = threading.Lock()


def store() -> Store:
    """The hub DB (paths.hub_db, env D4GC_HUB_DB). Seeds the demo volunteers on first use."""
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            path = load()["paths"]["hub_db"]
            path.parent.mkdir(parents=True, exist_ok=True)
            _STORE = Store(path)
            if not _STORE.one("SELECT 1 AS x FROM volunteers LIMIT 1"):
                _print_pins(seed_demo(_STORE))
    return _STORE


# --------------------------------------------------------------------------- credentials
def hash_pin(pin: str, salt: bytes) -> str:
    return hashlib.scrypt(pin.encode("utf-8"), salt=salt, **SCRYPT).hex()


def verify_pin(pin: str, cred: dict) -> bool:
    return hmac.compare_digest(hash_pin(pin, bytes.fromhex(cred["salt"])), cred["pin_hash"])


def new_pin() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def add_credential(st: Store, volunteer_id: str, pin: str, active: bool, username: str | None = None) -> str:
    """Insert a credential. A username is never reused (UNIQUE + old rows kept). Returns the username."""
    salt = secrets.token_bytes(16)
    for _ in range(10):
        name = username or f"v{secrets.token_hex(4)}"
        if not st.one("SELECT 1 AS x FROM credentials WHERE username = ?", (name,)):
            break
        if username:
            raise ValueError(f"username {username!r} already used")
    st.x("INSERT INTO credentials (volunteer_id, username, pin_hash, salt, created_at, active, delivered_at) "
         "VALUES (?,?,?,?,?,?,?)",
         (volunteer_id, name, hash_pin(pin, salt), salt.hex(), iso(CLOCK.now()), int(active),
          iso(CLOCK.now()) if active else None))
    return name


def auth_event(volunteer_id: str | None, event: str, ok: bool, detail: str = "") -> None:
    """Audit row. Callers must never pass a PIN or a raw token in ``detail``."""
    store().x("INSERT INTO auth_log (ts, volunteer_id, event, ok, detail) VALUES (?,?,?,?,?)",
              (iso(CLOCK.now()), volunteer_id, event, int(ok), detail))
    log.info("auth %s %s ok=%s %s", event, volunteer_id, ok, detail)


def expire(volunteer_id: str, why: str) -> None:
    """Mark the account expired. Its sessions die on their next request (current_volunteer)."""
    store().x("UPDATE volunteers SET status = 'expired' WHERE volunteer_id = ?", (volunteer_id,))
    auth_event(volunteer_id, "expire", True, why)


DEMO_VOLUNTEERS = [  # (volunteer_id, username, full_name, grp, role, mission_end offset in days)
    ("vol-amina", "dr_amina", "Dr Amina Yusuf", "medical", "volunteer", 182),
    ("vol-karim", "log_karim", "Karim Haddad", "field_ops", "volunteer", 90),
    ("vol-lea", "comms_lea", "Léa Martin", "communications", "volunteer", 90),
    ("vol-tom", "old_tom", "Tom Becker", "medical", "volunteer", -1),
    ("vol-sara", "admin_sara", "Sara Okafor", "admin_legal", "admin", 365),
]


def seed_demo(st: Store) -> dict[str, str]:
    """Wipe and re-create the demo volunteers. Returns {username: pin} (shown once by the caller)."""
    now = CLOCK.now()
    pins: dict[str, str] = {}
    with st.tx():
        for table in ("sessions", "credentials", "volunteers", "auth_log"):
            st.x(f"DELETE FROM {table}")
        for vid, username, name, grp, role, days in DEMO_VOLUNTEERS:
            st.x("INSERT INTO volunteers VALUES (?,?,?,?,?,?,?,?,?,0)",
                 (vid, name, grp, role, "active", iso(now - timedelta(days=30)), iso(now + timedelta(days=days)),
                  iso(now), iso(now + timedelta(days=rotation.ROTATION_DAYS))))
            pins[username] = new_pin()
            add_credential(st, vid, pins[username], active=True, username=username)
    _failures.clear()
    return pins


def _print_pins(pins: dict[str, str]) -> None:
    print("\n=== DEMO VOLUNTEER PINS (shown once, not stored in clear) ===", file=sys.stderr)
    for user, pin in pins.items():
        print(f"    {user:<12} PIN {pin}", file=sys.stderr)
    print("=== reset with: python -m hub.auth --reset-demo ===\n", file=sys.stderr, flush=True)


def public(vol: dict) -> dict:
    keys = ("volunteer_id", "full_name", "grp", "role", "status", "mission_end", "next_rotation", "rotation_pending")
    return {k: vol[k] for k in keys}


def account_problem(vol: dict) -> str | None:
    """None if the account may be used right now; else why not. Expiry is applied on the spot."""
    if vol["status"] != "active":
        return vol["status"]
    if parse(vol["mission_end"]) <= CLOCK.now():
        expire(vol["volunteer_id"], "mission ended (checked at request)")
        return "expired"
    return None


# --------------------------------------------------------------------------- rate limit
_failures: dict[str, deque] = defaultdict(deque)
_fail_lock = threading.Lock()


def _rate_limited(username: str) -> bool:
    with _fail_lock:
        q = _failures[username]
        while q and time.monotonic() - q[0] > RATE_WINDOW_S:
            q.popleft()
        return len(q) >= RATE_LIMIT


def _record_failure(username: str) -> None:
    with _fail_lock:
        _failures[username].append(time.monotonic())


# --------------------------------------------------------------------------- dependencies
def _token(request: Request, scope: str) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(COOKIE[scope])


def _session_volunteer(request: Request, scope: str) -> dict:
    token = _token(request, scope)
    if not token:
        raise HTTPException(401, "Not signed in")
    st = store()
    sess = st.one("SELECT * FROM sessions WHERE token = ?", (hashlib.sha256(token.encode()).hexdigest(),))
    if not sess or parse(sess["expires_at"]) <= session_now():
        raise HTTPException(401, "Session expired: sign in again")
    vol = st.one("SELECT * FROM volunteers WHERE volunteer_id = ?", (sess["volunteer_id"],))
    if not vol or account_problem(vol):
        st.x("DELETE FROM sessions WHERE volunteer_id = ?", (sess["volunteer_id"],))
        raise HTTPException(401, ENDED_MESSAGE)
    return vol


def current_volunteer(request: Request) -> dict:
    """FastAPI dependency: the signed-in, active, in-mission volunteer (re-checked every request)."""
    return _session_volunteer(request, "volunteer")


def current_admin(request: Request) -> dict:
    vol = _session_volunteer(request, "admin")
    if vol["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return vol


# --------------------------------------------------------------------------- routes
router = APIRouter()


class LoginBody(BaseModel):
    username: str
    pin: str
    scope: str = "volunteer"          # 'volunteer' (device page) | 'admin' (hub Volunteers panel)


@router.post("/auth/login")
def login(body: LoginBody, response: Response) -> dict:
    username = body.username.strip()[:64]
    scope = body.scope if body.scope in COOKIE else "volunteer"
    if _rate_limited(username):
        auth_event(None, "login", False, f"rate limited: {username}")
        raise HTTPException(429, "Too many attempts. Wait 5 minutes.")
    st = store()
    cred = st.one("SELECT * FROM credentials WHERE username = ?", (username,))
    pin_ok = verify_pin(body.pin, cred) if cred else (hash_pin(body.pin, b"0" * 16) and False)  # same cost
    vol = st.one("SELECT * FROM volunteers WHERE volunteer_id = ?", (cred["volunteer_id"],)) if cred else None
    if not cred:
        why = "unknown username"
    elif not cred["active"]:
        why = "credential inactive"
    elif not pin_ok:
        why = "wrong PIN"
    elif not vol:
        why = "no volunteer record"
    else:
        why = account_problem(vol)
        if not why and scope == "admin" and vol["role"] != "admin":
            why = "not an admin"
    if why:
        _record_failure(username)
        auth_event(vol["volunteer_id"] if vol else None, "login", False, f"{username}: {why}")
        raise HTTPException(401, GENERIC_ERROR)

    token = secrets.token_urlsafe(32)
    expires = session_now() + timedelta(hours=SESSION_HOURS)
    st.x("INSERT INTO sessions (token, volunteer_id, expires_at) VALUES (?,?,?)",
         (hashlib.sha256(token.encode()).hexdigest(), vol["volunteer_id"], iso(expires)))
    response.set_cookie(COOKIE[scope], token, httponly=True, samesite="strict", max_age=SESSION_HOURS * 3600, path="/")
    auth_event(vol["volunteer_id"], "login", True, f"{username} ({scope})")
    return {"token": token, "expires_at": iso(expires), "volunteer": public(vol)}


@router.post("/auth/logout")
def logout(request: Request, response: Response, scope: str = "volunteer") -> dict:
    scope = scope if scope in COOKIE else "volunteer"
    token = _token(request, scope)
    if token:
        st = store()
        h = hashlib.sha256(token.encode()).hexdigest()
        sess = st.one("SELECT volunteer_id FROM sessions WHERE token = ?", (h,))
        st.x("DELETE FROM sessions WHERE token = ?", (h,))
        auth_event(sess["volunteer_id"] if sess else None, "logout", True, scope)
    response.delete_cookie(COOKIE[scope], path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(vol: dict = Depends(current_volunteer)) -> dict:
    return {"volunteer": public(vol), "now": iso(CLOCK.now())}


@router.get("/auth/admin/me")
def admin_me(vol: dict = Depends(current_admin)) -> dict:
    return {"volunteer": public(vol), "now": iso(CLOCK.now())}


@router.get("/admin/volunteers")
def list_volunteers(_: dict = Depends(current_admin)) -> dict:
    st = store()
    rows = []
    for vol in st.q("SELECT * FROM volunteers ORDER BY role DESC, full_name"):
        vid = vol["volunteer_id"]
        active = st.one("SELECT username FROM credentials WHERE volunteer_id = ? AND active = 1", (vid,))
        waiting = st.one("SELECT username FROM credentials WHERE volunteer_id = ? AND active = 0 AND delivered_at IS NULL",
                         (vid,))
        sessions = st.one("SELECT count(*) AS n FROM sessions WHERE volunteer_id = ?", (vid,))["n"]
        rows.append({**public(vol), "username": active["username"] if active else None,
                     "awaiting_delivery": waiting["username"] if waiting else None,
                     "reveal_available": rotation.reveal_available(vid), "sessions": sessions})
    return {"volunteers": rows, "now": iso(CLOCK.now()),
            "clock_offset_days": round(CLOCK.offset.total_seconds() / 86400, 2),
            "power": POWER.get_power_status(), "power_label": getattr(POWER, "LABEL", ""),
            "auth_log": st.q("SELECT * FROM auth_log ORDER BY rowid DESC LIMIT 20")}


@router.post("/admin/volunteers/{volunteer_id}/{action}")
def volunteer_action(volunteer_id: str, action: str, admin: dict = Depends(current_admin)) -> dict:
    st = store()
    vol = st.one("SELECT * FROM volunteers WHERE volunteer_id = ?", (volunteer_id,))
    if not vol:
        raise HTTPException(404, "unknown volunteer")
    now = CLOCK.now()
    by = f"by {admin['volunteer_id']}"
    if action == "deactivate":
        st.x("UPDATE volunteers SET status = 'inactive' WHERE volunteer_id = ?", (volunteer_id,))
        auth_event(volunteer_id, "deactivate", True, by)   # sessions die on their next request
    elif action == "activate":
        if parse(vol["mission_end"]) <= now:
            raise HTTPException(409, "Mission has ended: extend the mission first")
        st.x("UPDATE volunteers SET status = 'active' WHERE volunteer_id = ?", (volunteer_id,))
        auth_event(volunteer_id, "activate", True, by)
    elif action == "extend":
        end = max(parse(vol["mission_end"]), now) + timedelta(days=30)
        status = "active" if vol["status"] == "expired" else vol["status"]
        st.x("UPDATE volunteers SET mission_end = ?, status = ? WHERE volunteer_id = ?", (iso(end), status, volunteer_id))
        auth_event(volunteer_id, "extend", True, f"mission end -> {iso(end)} {by}")
    elif action == "rotate":
        try:
            rotation.rotate(volunteer_id, f"manual {by}")
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    elif action == "confirm":
        try:
            rotation.confirm_delivered(volunteer_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    elif action == "reveal":
        secret = rotation.reveal_once(volunteer_id)
        if not secret:
            raise HTTPException(404, "Already shown (or nothing to show). Rotate again if it was lost.")
        auth_event(volunteer_id, "rotation", True, f"new credential shown once to admin {by}")
        return {"volunteer_id": volunteer_id, **secret, "note": "Hand to the volunteer. This is shown only once."}
    else:
        raise HTTPException(404, "unknown action")
    return {"ok": True, "volunteer": public(st.one("SELECT * FROM volunteers WHERE volunteer_id = ?", (volunteer_id,)))}


class PowerBody(BaseModel):
    status: str


@router.post("/admin/power")
def set_power(body: PowerBody, admin: dict = Depends(current_admin)) -> dict:
    if not hasattr(POWER, "set_status"):
        raise HTTPException(409, "power comes from a real monitor")
    try:
        POWER.set_status(body.status)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    auth_event(admin["volunteer_id"], "power", True, f"simulated power -> {body.status}")
    return {"power": body.status, "scheduler": rotation.run_scheduler()}


class ClockBody(BaseModel):
    days: float = 7


@router.post("/admin/clock")
def advance_clock(body: ClockBody, admin: dict = Depends(current_admin)) -> dict:
    CLOCK.advance(body.days)
    auth_event(admin["volunteer_id"], "clock", True, f"demo clock {body.days:+g} days")
    return {"now": iso(CLOCK.now()), "scheduler": rotation.run_scheduler()}


if __name__ == "__main__":
    if "--reset-demo" in sys.argv:
        _print_pins(seed_demo(store()))
    else:
        print(__doc__)
