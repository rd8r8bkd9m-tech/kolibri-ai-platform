# Rollback And Smoke Tests

## Rollback

No live service restart or production deploy was performed in this task.

If canary deploy of this branch causes regression:

1. Remove the canary environment override:

```bash
unset KOLIBRI_FACTORY_CONTROL_URLS
unset FACTORY_STATUS_REQUIRED_TIMEOUT
unset FACTORY_STATUS_CONNECT_TIMEOUT
unset FACTORY_STATUS_FETCH_TASKS
```

2. Restore the previous backend artifact or checkout the previous deployed release for `backend/factory_status.py`.

3. Restart only the backend service that serves `/api/factory/status`.

4. Re-run the smoke tests below.

If only the selected Control Plane route is bad, rollback can be limited to:

```bash
KOLIBRI_FACTORY_CONTROL_URLS=http://10.99.0.2:9101
FACTORY_STATUS_FETCH_TASKS=0
```

## Smoke Tests

Run from a server Agent Host, not a local Mac:

```bash
curl --max-time 3 -fsS http://10.99.0.10:9101/v1/health >/tmp/kolibri-cp-health.json
curl --max-time 3 -fsS http://10.99.0.10:9101/v1/nodes >/tmp/kolibri-cp-nodes.json
curl --max-time 5 -fsS http://127.0.0.1:8000/api/factory/status >/tmp/kolibri-factory-status.json
python3 -m json.tool /tmp/kolibri-factory-status.json >/tmp/kolibri-factory-status.pretty.json
```

Expected canary status:

- HTTP 200 from backend `/api/factory/status`.
- JSON includes `source=control-plane`.
- JSON includes `control_plane.status=ok`.
- JSON includes `control_plane.url=http://10.99.0.10:9101` when the recommended canary env is active.
- Total backend request time stays under 5 seconds.

Public smoke is currently blocked until the edge TLS/request-routing issue is repaired:

```bash
curl --max-time 8 -fsS https://kolibriai.ru/api/factory/status
```

