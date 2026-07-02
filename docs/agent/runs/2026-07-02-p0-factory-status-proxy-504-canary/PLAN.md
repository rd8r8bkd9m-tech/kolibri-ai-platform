# P0 Factory Status Proxy 504 Canary Plan

Task: `P0_FACTORY_STATUS_PROXY_504_CANARY_2026_07_02`

Node: `kolibri`

Branch: `agent/P0_FACTORY_STATUS_PROXY_504_CANARY_2026_07_02/generic`

Goal: repair or prepare a safe canary for `https://kolibriai.ru/api/factory/status` timing out or returning 504 while Control Plane health is good.

## Diagnosis

The backend status adapter made sequential upstream calls to `/v1/health`, `/v1/nodes`, then optional `/v1/tasks`.

Live probes from the server node showed:

- `http://10.99.0.2:9101/v1/health`: HTTP 200, about 0.10s.
- `http://10.99.0.2:9101/v1/nodes`: HTTP 200, about 6.45s.
- `http://10.99.0.10:9101/v1/health`: HTTP 200, about 0.002s.
- `http://10.99.0.10:9101/v1/nodes`: HTTP 200, about 0.03s.
- `http://10.99.0.10:9101/v1/tasks`: HTTP 200, about 0.57s but about 15 MB.

The 504 risk is therefore not Control Plane health. It is the status adapter depending on a slow nodes route and a large optional tasks payload.

## Repair

Implemented a bounded adapter canary:

- Support ordered `KOLIBRI_FACTORY_CONTROL_URLS` with fallback.
- Fetch required health and nodes concurrently.
- Bound required route attempts with `FACTORY_STATUS_REQUIRED_TIMEOUT`, default `2.0`.
- Bound connect time with `FACTORY_STATUS_CONNECT_TIMEOUT`, default `0.5`.
- Skip `/v1/tasks` by default because the live payload is large; enable only with `FACTORY_STATUS_FETCH_TASKS=1`.
- Normalize the canonical `/v1/health` envelope where `status=completed` and health data is nested under `data`.
- Keep response shape compatible with the existing frontend.

## Canary Settings

Recommended first canary environment:

```bash
KOLIBRI_FACTORY_CONTROL_URLS=http://10.99.0.10:9101,http://10.99.0.2:9101
FACTORY_STATUS_REQUIRED_TIMEOUT=2.0
FACTORY_STATUS_CONNECT_TIMEOUT=0.5
FACTORY_STATUS_FETCH_TASKS=0
```

Expected backend result: `/api/factory/status` returns from the fast Control Plane listener and reports `control_plane.url=http://10.99.0.10:9101`.

