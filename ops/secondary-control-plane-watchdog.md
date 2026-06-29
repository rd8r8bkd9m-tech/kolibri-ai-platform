# Secondary Control Plane Watchdog

- Last checked: 2026-06-29T05:56:03Z
- Status: degraded
- GitHub issue: `#53`
- Symptom: `GET /health` still returns `status=ok` with `redis=PONG`, but `GET /v1/tasks?summary=1&compact=1` still shows `73` queued tasks and `0` active while `GET /v1/nodes` returns `35` total nodes with only `6` `online` and `29` `stale`; both surfaced `active_task` node cards remain on `stale` nodes in `dead_letter`.
- Impact: Secondary Control Plane remains reachable and Redis remains healthy, but dispatch confidence is still degraded. Operators cannot trust the surfaced node roster to reflect runnable capacity, and the queue remains stuck with no active work surfaced by the compact task summary.
- Last successful full check: none recorded by this watchdog yet
- Last successful partial checks:
  - `GET /health` at `2026-06-29T05:55:16.521728+00:00` with `queue_backend=redis`, `redis=PONG`, `status=ok`
  - `GET /v1/nodes` during the `2026-06-29T05:56Z` probe window with `35` total nodes, `6` `online`, `29` `stale`, `3` draining nodes, and `2` stale nodes still surfacing `active_task`
  - `GET /v1/tasks?summary=1&compact=1` during the `2026-06-29T05:56Z` probe window with `73` queued tasks surfaced and `0` active

## Current Snapshot

- Queue backend: `redis`
- Redis: `PONG`
- Control Plane health: `ok`
- `/health` time: `2026-06-29T05:55:16.521728+00:00`
- `/v1/nodes` result: returned successfully during the `2026-06-29T05:56Z` probe window
- `/v1/tasks` result: returned successfully during the `2026-06-29T05:56Z` probe window
- Nodes: `35 total`
- Node health mix: `6 online`, `29 stale`
- Draining nodes: `3`
- Online nodes: `home`, `home-live`, `main`, `new`, `qjns`, `uiap`
- Active task nodes: `2`, both `stale`
- Oldest stale heartbeat sample: `macbook` last heartbeat `2026-06-28T04:31:47.381247+00:00` (`91456s` old during probe)
- Task queue: `73 queued`, `0` running surfaced by `/v1/tasks?summary=1&compact=1`
- Oldest queued task: `KOL-NETWORK-CONVERGENCE-001-NODE-KOLIBRI_217_60_252_10-PROBE-001` created `2026-06-25T18:45:00.500947+00:00`
- Newest queued task: `KOL-SERVER-KFRM-RUNTIME-RECOVERY-20260629` created `2026-06-29T05:43:57.963045+00:00`
- Surfaced stale active tasks:
  - `9fts` -> `TG-20260629003017-4711-up-telegram` (`dead_letter`)
  - `primary-candidate` -> `KOL-META-MIMO-ORCHESTRATOR-PRIMARY-20260629` (`dead_letter`)

## Heartbeat Status

- Heartbeat verdict: degraded but reachable
- Heartbeat summary: `GET /health` remains healthy enough to answer and Redis remains `PONG`, but scheduler-facing state is still unhealthy because most nodes remain `stale` and no active work is surfaced despite a non-empty queue.

## Safe Recovery Steps

1. Re-run read-only probes for `/health`, `/v1/nodes`, and `/v1/tasks?summary=1&compact=1` to confirm whether the stale-node majority and stuck queue persist.
2. Inspect Control Plane logs and node heartbeat ingestion or freshness evaluation paths for lag, dropped updates, or classification drift, without restarting services.
3. Check whether Redis-backed heartbeat keys are still updating on time and whether recent threshold or classification changes could explain `29` nodes remaining `stale`.
4. Review why `73` tasks remain `queued` while only `6` nodes are `online`; verify scheduler placement, lease issuance, and whether stale-node filtering is preventing dispatch.
5. After remediation, verify a healthy node-state mix with active dispatch resuming, then record the first successful healthy full check. Do not restart the Control Plane or Redis without explicit approval.
