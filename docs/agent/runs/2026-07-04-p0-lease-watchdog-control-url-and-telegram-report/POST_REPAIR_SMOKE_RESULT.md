# Post-Repair Smoke Result

Command mode: `--diagnose-only`.

Mutation:

- Queue POST: no.
- Redis cleanup: no.
- Telegram send: no.
- Service restart: no.

Result:

```json
{
  "status": "diagnosed",
  "control_plane_used": "http://10.99.0.1:9101",
  "redis": "PONG",
  "queue_seen": 100,
  "expired_leases": 0,
  "stuck_heartbeat_tasks": null,
  "failed_candidates": [
    {"url": "http://10.99.0.2:9101", "reason": "timed out"},
    {"url": "http://10.99.0.10:9101", "reason": "timed out"}
  ]
}
```

Interpretation:

- Watchdog no longer blocks on the first dead URL.
- Current authoritative endpoint from `server-kfrm` is `http://10.99.0.1:9101`.
- The owner report can now show "не проверено" rather than raw `None`.
