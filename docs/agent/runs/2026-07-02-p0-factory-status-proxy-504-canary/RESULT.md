# Result

Status: `prepared_safe_canary`

Node: `kolibri`

Head SHA at implementation time: `f7ac32c70406432a52752ca45d87e35d9f1facd3`

Changed files:

- `backend/factory_status.py`
- `backend/tests/test_factory_status_fast_health.py`
- `docs/agent/runs/2026-07-02-p0-factory-status-proxy-504-canary/PLAN.md`
- `docs/agent/runs/2026-07-02-p0-factory-status-proxy-504-canary/ACTIONS.md`
- `docs/agent/runs/2026-07-02-p0-factory-status-proxy-504-canary/TESTS.md`
- `docs/agent/runs/2026-07-02-p0-factory-status-proxy-504-canary/ROLLBACK.md`
- `docs/agent/runs/2026-07-02-p0-factory-status-proxy-504-canary/RESULT.md`
- `docs/agent/runs/2026-07-02-p0-factory-status-proxy-504-canary/NEXT.md`
- `docs/agent/runs/2026-07-02-p0-factory-status-proxy-504-canary/REMOTE_RESULT.json`

## Exact State

The Control Plane is healthy internally, but the old status adapter could still breach proxy budgets because one nodes route was slow and `/v1/tasks` can be very large.

Prepared code repair:

- Required upstream calls are now concurrent and bounded.
- Ordered Control Plane route fallback is available through `KOLIBRI_FACTORY_CONTROL_URLS`.
- Optional task aggregation is disabled by default through `FACTORY_STATUS_FETCH_TASKS=0`.
- Canonical Fabric `/v1/health` envelopes are normalized to `control_plane.status=ok`.

## Blockers

- Strict public HTTPS verification for `https://kolibriai.ru` failed from this server because the certificate does not match the hostname.
- Insecure public HTTPS returned HTTP 400 `Invalid request`.
- Public HTTP returned an empty reply.
- Because of those edge blockers, I did not claim production public endpoint recovery and did not restart live services.

## Verification

- `python3 -m pytest backend/tests/test_factory_status_fast_health.py tests/test_factory_status.py -q`: `8 passed in 0.06s`.
- `python3 -m py_compile backend/factory_status.py backend/main.py`: passed.
- `git diff --check`: passed.
- Live internal probes proved `10.99.0.10:9101` is the safe canary route for health/nodes and `10.99.0.2:9101` is the slow fallback route.

## Next Action

Deploy this branch to one backend canary with:

```bash
KOLIBRI_FACTORY_CONTROL_URLS=http://10.99.0.10:9101,http://10.99.0.2:9101
FACTORY_STATUS_FETCH_TASKS=0
```

Then run backend-local smoke against `http://127.0.0.1:8000/api/factory/status`. Separately repair the public edge TLS/request-routing issue before claiming `https://kolibriai.ru/api/factory/status` is fixed.

