# Security notes (volunteer login, hackathon demo)

Built: local volunteer accounts (scrypt-hashed 6-digit PINs), 8 h sessions (only the SHA-256 of the
token is stored), status + mission end re-checked on every request, generic login error,
5 failures / username / 5 min rate limit, weekly credential rotation with admin-confirmed delivery,
rotation deferred during power outages, auth audit log without PINs.

## Known gaps in this demo
- `/admin/budget`, `/admin/connectivity` and `/requests/{id}/approve|reject` are still open (kept so the
  existing demo works). They must require `current_admin` before field use.
- A 6-digit PIN is weak: the rate limit is per username only. Add per-device/IP limits and lockout alerts.
- Cookies are not `Secure` because the demo runs over plain HTTP on 127.0.0.1.
- The demo clock offset and the power state are in memory and reset when the hub restarts.
- Credential rotation does not end existing sessions (they expire after 8 h).

## TODO (out of scope, not built)
- [ ] HTTPS/TLS certificates on the hub (local CA for the mission network).
- [ ] Encryption at rest of the device cache (documents and catalog on staff devices).
- [ ] Secure out-of-band credential delivery (SMS / radio / sealed card) instead of "admin reads it aloud".
- [ ] Real UPS hardware: replace `SimulatedPowerMonitor` with a NUT (`upsc`) integration.
- [ ] Offline login on devices with signed, time-bounded tokens (works when the hub is unreachable).
- [ ] Rotation of admin keys / admin credentials (admins are excluded from auto-rotation today).
