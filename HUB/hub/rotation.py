"""Weekly credential rotation, power rule and the demo clock.

Rules:
- Every 7 days an active volunteer gets a new random username + 6-digit PIN. The new credential
  is stored inactive, shown ONCE to the admin ("hand to volunteer"), and only becomes active
  (and the old one inactive) when the admin clicks "Confirmed delivered".
- Power rule: if power is 'outage' or 'battery', rotation is deferred (rotation_pending=1) and
  the old credential stays valid: nobody should be locked out while the generator is down.
  When power is back to 'mains', pending rotations run. Internet status is a separate thing.
- Mission expiry ALWAYS wins: an expired or deactivated account never logs in, pending or not.
- Admin volunteers are not auto-rotated (admin key rotation is a TODO, see docs/SECURITY_NOTES.md).
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

from common.log import get_logger

log = get_logger("rotation")
ROTATION_DAYS = 7
SCHEDULER_INTERVAL_S = 60
DEFER_POWER = ("outage", "battery")


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


class DemoClock:
    """Real UTC time plus an admin-controlled offset (demo only). Use CLOCK.now(), not datetime.now()."""

    def __init__(self) -> None:
        self.offset = timedelta(0)

    def now(self) -> datetime:
        return datetime.now(timezone.utc) + self.offset

    def advance(self, days: float) -> None:
        self.offset += timedelta(days=days)
        log.info("DEMO CLOCK advanced %+g days -> %s", days, iso(self.now()))

    def reset(self) -> None:
        self.offset = timedelta(0)


class PowerMonitor:
    """Interface: where the hub learns its power state."""

    STATES = ("mains", "battery", "outage", "unknown")

    def get_power_status(self) -> str:  # 'mains' | 'battery' | 'outage' | 'unknown'
        raise NotImplementedError


class SimulatedPowerMonitor(PowerMonitor):
    """SIMULATED - replace with UPS/NUT integration.

    A real version would read the UPS through NUT (`upsc <ups>@localhost ups.status`:
    'OL' = on line/mains, 'OB' = on battery, 'LB' = low battery). Never infer power from internet.
    """

    LABEL = "SIMULATED - replace with UPS/NUT integration"

    def __init__(self) -> None:
        self._status = "mains"

    def get_power_status(self) -> str:
        return self._status

    def set_status(self, status: str) -> None:
        if status not in self.STATES:
            raise ValueError(f"power status must be one of {self.STATES}")
        log.info("POWER (simulated): %s -> %s", self._status, status)
        self._status = status


CLOCK = DemoClock()
POWER: PowerMonitor = SimulatedPowerMonitor()
_reveal: dict[str, dict] = {}       # volunteer_id -> {username, pin}: memory only, popped when shown
_reveal_lock = threading.Lock()


def rotate(volunteer_id: str, reason: str = "manual") -> dict:
    """Generate a new credential (inactive until delivery is confirmed). Returns no PIN."""
    from hub import auth

    st = auth.store()
    vol = st.one("SELECT * FROM volunteers WHERE volunteer_id = ?", (volunteer_id,))
    if not vol or vol["status"] != "active":
        raise ValueError("only active volunteers can be rotated")
    now = CLOCK.now()
    pin = auth.new_pin()
    with st.tx():
        st.x("UPDATE credentials SET delivered_at = ? WHERE volunteer_id = ? AND active = 0 AND delivered_at IS NULL",
             (f"discarded {iso(now)}", volunteer_id))   # an older undelivered credential can never be activated
        username = auth.add_credential(st, volunteer_id, pin, active=False)
        st.x("UPDATE volunteers SET last_rotation = ?, next_rotation = ?, rotation_pending = 0 WHERE volunteer_id = ?",
             (iso(now), iso(now + timedelta(days=ROTATION_DAYS)), volunteer_id))
    with _reveal_lock:
        _reveal[volunteer_id] = {"username": username, "pin": pin}
    auth.auth_event(volunteer_id, "rotation", True, f"{reason}: new credential {username} awaiting delivery")
    return {"volunteer_id": volunteer_id, "username": username, "awaiting_delivery": True}


def reveal_once(volunteer_id: str) -> dict | None:
    """Return the new username + PIN exactly once (then it is gone from memory)."""
    with _reveal_lock:
        return _reveal.pop(volunteer_id, None)


def reveal_available(volunteer_id: str) -> bool:
    with _reveal_lock:
        return volunteer_id in _reveal


def confirm_delivered(volunteer_id: str) -> dict:
    """Admin confirmed the volunteer has the new credential: activate it, deactivate the old one."""
    from hub import auth

    st = auth.store()
    new = st.one("""SELECT username FROM credentials WHERE volunteer_id = ? AND active = 0 AND delivered_at IS NULL
                    ORDER BY created_at DESC LIMIT 1""", (volunteer_id,))
    if not new:
        raise ValueError("no credential is awaiting delivery")
    now = iso(CLOCK.now())
    with st.tx():
        st.x("UPDATE credentials SET active = 0 WHERE volunteer_id = ? AND active = 1", (volunteer_id,))
        st.x("UPDATE credentials SET active = 1, delivered_at = ? WHERE username = ?", (now, new["username"]))
    with _reveal_lock:
        _reveal.pop(volunteer_id, None)
    auth.auth_event(volunteer_id, "rotation", True, f"delivery confirmed: {new['username']} active, old credential off")
    return {"volunteer_id": volunteer_id, "active_username": new["username"]}


def run_scheduler() -> dict:
    """One scheduler pass: expire ended missions, then rotate (or defer) due credentials."""
    from hub import auth

    st = auth.store()
    now, power = CLOCK.now(), POWER.get_power_status()
    actions: dict[str, list] = {"expired": [], "rotated": [], "pending": [], "power": power}
    for vol in st.q("SELECT * FROM volunteers WHERE status = 'active'"):
        vid = vol["volunteer_id"]
        if parse(vol["mission_end"]) <= now:          # expiry always wins
            auth.expire(vid, "mission ended (scheduler)")
            actions["expired"].append(vid)
            continue
        if vol["role"] == "admin":
            continue
        due = vol["rotation_pending"] or (vol["next_rotation"] and parse(vol["next_rotation"]) <= now)
        if not due:
            continue
        if power in DEFER_POWER:
            if not vol["rotation_pending"]:
                st.x("UPDATE volunteers SET rotation_pending = 1 WHERE volunteer_id = ?", (vid,))
                auth.auth_event(vid, "rotation", False, f"deferred: power={power}, old credential stays valid")
            actions["pending"].append(vid)
        else:
            rotate(vid, "pending rotation, power back" if vol["rotation_pending"] else "weekly rotation")
            actions["rotated"].append(vid)
    if actions["expired"] or actions["rotated"] or actions["pending"]:
        log.info("scheduler: %s", actions)
    return actions


def start_scheduler(interval_s: int = SCHEDULER_INTERVAL_S) -> threading.Thread:
    """Background thread: one pass every ``interval_s`` seconds (daemon, dies with the hub)."""

    def loop() -> None:
        while True:
            time.sleep(interval_s)
            try:
                run_scheduler()
            except Exception:  # never kill the hub because of the scheduler
                log.exception("scheduler pass failed")

    thread = threading.Thread(target=loop, name="rotation-scheduler", daemon=True)
    thread.start()
    return thread
