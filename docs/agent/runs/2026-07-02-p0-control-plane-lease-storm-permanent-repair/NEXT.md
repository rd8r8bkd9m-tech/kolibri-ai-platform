# Next

Next exact task:

`P0_CONTROL_PLANE_LEASE_STORM_RUNTIME_CANARY_2026_07_02`

Canary scope:

1. Deploy this branch to `primary-candidate` Control Plane and one Agent Host only.
2. Keep the reduced worker pool at first.
3. Verify `/v1/health`, `/v1/nodes`, `/v1/tasks?limit=100`, and `/v1/tasks/lease`.
4. Measure fd count, thread count, Redis clients, lease 5xx, health p95, task listing p95.
5. Increase polling pressure in stages: 20, 50, 100, 250, 500, 1000 logical agents.
6. Stop at the first failed gate and keep the last stable pool size.
7. Only after a green canary, retry PR #119 release gate.

Blocked items:

- Full pytest is blocked on this server by missing `pydantic` and `httpx`.
- Server-side push was blocked by a read-only SSH key, so Mac relayed the server-authored commit to GitHub as a thin-client action.
