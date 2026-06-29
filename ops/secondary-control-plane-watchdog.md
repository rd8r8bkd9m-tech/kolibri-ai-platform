# Secondary Control Plane Watchdog

- Last checked (UTC): 2026-06-29T12:29:04Z
- Status: OK
- Control Plane health: `/health`, `/v1/nodes`, and `/v1/tasks?summary=1&compact=1` returned `HTTP 200`
- Redis: `PONG`
- Last successful check (UTC): 2026-06-29T12:29:04Z

## Heartbeat

Secondary Control Plane responded normally on this run. `/health` reported `status=ok` with Redis `PONG`, `/v1/nodes` returned 5 registered nodes with 4 fresh canonical non-draining nodes, and `/v1/tasks?summary=1&compact=1` returned a compact queue summary with 2 queued probe tasks and 0 active tasks.

- Probe timestamps: `/health` at `2026-06-29T12:29:04.161786+00:00`, `/v1/nodes` at `2026-06-29T12:29:04Z`, `/v1/tasks?summary=1&compact=1` at `2026-06-29T12:29:04Z`
- Node note: `main`, `new`, `primary-candidate`, and `qjns` are fresh and online; `primary-candidate` is actively running `KOL-GOMESH-HOME-MIKROTIK-RECOVERY-20260629`; `smoke-primary` remains stale, not draining, with `heartbeat_age_seconds` about 6480.1 seconds in this snapshot
- Queue note: queued tasks remain `KOL-SUPER-ESTIMATOR-001-REMOTE-STATUS-9FTS` and `KOL-UIAP-KNOWLEDGE-REMOTE-STATUS-001`; there are no active lease-backed runs in the compact summary

## Impact

No immediate operator action is required from this watchdog run. The secondary contour is serving its read-only API, Redis health is observable, and queue visibility is intact. The only watch item in this snapshot is the stale `smoke-primary` registration, which does not currently block the read-only API.

## Last Successful Check

The latest successful watchdog verification is `2026-06-29T12:29:04Z`, when `/health`, `/v1/nodes`, and `/v1/tasks?summary=1&compact=1` all completed with `HTTP 200` and `/health` reported Redis `PONG`.

## Issue Handling

`gh` is available in this execution environment, but no GitHub issue was created or updated in this run because the control plane remained healthy and Redis returned `PONG`. No secrets were printed, no SSH was used, and no destructive restart was attempted.

## Safe Follow-up Steps

1. Keep watching the stale `smoke-primary` registration and confirm whether it should resume heartbeats or be retired from the registry.
2. Re-run the same three read-only probes on the next watchdog interval and compare fresh node counts plus queue length.
3. If `/health` stops returning Redis `PONG` or the API becomes unavailable again, replace the heartbeat section with an incident update that includes timestamps, impact, the last successful check, and safe recovery steps before considering any restart.
