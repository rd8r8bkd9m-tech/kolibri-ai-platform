# Secondary Control Plane Watchdog

- Last checked: 2026-06-29T05:26:28Z
- Status: degraded
- GitHub issue: `#53`
- Symptom: `GET /health` returned `status=ok` with `redis=PONG`, `GET /v1/tasks?summary=1&compact=1` returned `73` queued tasks, but `GET /v1/nodes` still showed only `5` fresh `online` nodes and `30` `stale` nodes out of `35` total.
- Impact: Secondary Control Plane is reachable and Redis is healthy, but node freshness remains heavily degraded. Operators still cannot trust worker availability or dispatch readiness from this surface, and the queued backlog increased from `71` to `73`.
- Last successful full check: none recorded by this watchdog yet
- Last successful partial checks:
  - `GET /health` at `2026-06-29T05:25:36.063157+00:00` with `queue_backend=redis`, `redis=PONG`, `status=ok`
  - `GET /v1/nodes` during the `2026-06-29T05:25Z` probe window with `35` total nodes, `5` `online`, `30` `stale`, `3` draining nodes, and `3` nodes with active tasks
  - `GET /v1/tasks?summary=1&compact=1` during the `2026-06-29T05:25Z` probe window with `73` tasks, all currently `queued`

## Current Snapshot

- Queue backend: `redis`
- Redis: `PONG`
- Control Plane health: `ok`
- `/health` time: `2026-06-29T05:25:36.063157+00:00`
- `/v1/nodes` result: returned successfully during the `2026-06-29T05:25Z` probe window
- `/v1/tasks` result: returned successfully during the `2026-06-29T05:25Z` probe window
- Nodes: `35 total`
- Node health mix: `5 online`, `30 stale`
- Fresh nodes: `5`
- Draining nodes: `3`
- Active task nodes: `3`
- Oldest stale heartbeat sample: `macbook` last heartbeat `2026-06-28T04:31:47.381247+00:00` (`89630s` old during probe)
- Task queue: `73 queued`, `0` running surfaced by `/v1/tasks?summary=1&compact=1`
- Primary candidate activity: recent orchestrator task traffic still targets `primary-candidate`

## Safe Recovery Steps

1. Re-run read-only probes for `/health`, `/v1/nodes`, and `/v1/tasks?summary=1&compact=1` to confirm whether the node freshness failure persists while task summary remains available.
2. Inspect Control Plane logs and node heartbeat ingestion paths for lag, dropped updates, or freshness evaluation errors, without restarting services.
3. Check whether Redis-backed heartbeat keys are updating on time and whether the Control Plane freshness threshold or clock skew is causing false `stale` classification.
4. Review why `73` tasks remain `queued` while only `5` nodes are fresh; verify scheduler placement, lease issuance, and whether stale-node filtering is blocking dispatch.
5. After remediation, verify a materially higher fresh-node count and record the first successful healthy full check. Do not restart the Control Plane or Redis without explicit approval.
