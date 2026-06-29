# Secondary Control Plane Watchdog

- Last checked (UTC): 2026-06-29T13:28:44Z
- Status: OK
- Control Plane health: `/health`, `/v1/nodes`, and `/v1/tasks?summary=1&compact=1` returned `HTTP 200`
- Redis: `PONG`
- Last successful check (UTC): 2026-06-29T13:28:44Z

## Heartbeat

Secondary Control Plane responded normally on this run. `/health` reported `status=ok` with Redis `PONG`, `/v1/nodes` returned 21 registered nodes with 20 fresh non-draining nodes, and `/v1/tasks?summary=1&compact=1` returned 2 queued tasks with 0 active tasks and 0 expired leases.

- Probe timestamps: `/health` at `2026-06-29T13:28:44.422705+00:00`; `/v1/nodes` completed in the same check window with `primary-candidate` heartbeat at `2026-06-29T13:28:47.185593+00:00`; `/v1/tasks?summary=1&compact=1` matched a 2-task queue snapshot from the same run
- Node note: fresh online nodes include `main`, `new`, `qjns`, `primary-candidate`, and 16 mesh nodes; `smoke-primary` remains long-stale and non-draining, but it is the only stale registration in this snapshot
- Queue note: queued tasks are `KOL-SUPER-ESTIMATOR-001-REMOTE-STATUS-9FTS` and `KOL-UIAP-KNOWLEDGE-REMOTE-STATUS-001`

## Impact

No immediate operator action is required for the secondary contour. The read-only API is available, Redis health is observable, and queue visibility is intact. The only watch item from this run is the long-stale `smoke-primary` registration, while the standby-capable `primary-candidate` node is fresh again.

## Last Successful Check

The latest successful watchdog verification is `2026-06-29T13:28:44Z`, when `/health`, `/v1/nodes`, and `/v1/tasks?summary=1&compact=1` all completed with `HTTP 200` and `/health` reported Redis `PONG`.

## Issue Handling

`gh` is available and authenticated in this environment, but no GitHub issue was created or updated in this run because the Control Plane remained reachable and Redis did not regress from `PONG`. No secrets were printed, no SSH was used, and no destructive restart was attempted.

## Safe Follow-up Steps

1. Re-check whether `primary-candidate` resumes fresh heartbeats while `KOL-FORMULALM-SCIENTIFIC-RD-20260629` is still attached; if it stays stale across the next interval, treat that as a separate availability risk for the standby path.
2. Keep watching the long-stale `smoke-primary` registration and confirm whether it should resume heartbeats or be retired from the registry.
3. If `/health` stops returning Redis `PONG` or the API becomes unavailable, replace this heartbeat with an incident update that includes timestamps, impact, the last successful check, safe recovery steps, and a linked GitHub issue labeled `P0` and `factory`.
