# Queue Diagnostics Report

Before this branch, live `/v1/tasks/queue/diagnostics` returned 404.

This branch adds `queue_diagnostics()` and `GET /v1/tasks/queue/diagnostics`.

## Live Snapshot Used

- Queue total after network repair task creation: 19.
- Leaseable after network repair task creation: 19.
- Blocked after production deploy: 0.
- Total task IDs: 21978.
- Endpoint latency after bounding state scan: about 0.22s in the live check.

## Network Repair Tasks Created

- `P0_REPAIR_FACTORY_SSH_TRUST_BOOTSTRAP_20260703`
- `P0_REPAIR_AGENT10_NETWORK_OR_RETIRE_20260703`
- `P0_REPAIR_DEGRADED_EXECUTION_NODES_20260703`
- `P0_CLASSIFY_STALE_RESERVE_SERVERS_20260703`
- `P0_PROVE_TELEGRAM_ACTIVE_OWNER_PATH_20260703`
- `P0_MIMO_BOUNDED_CANARY_WITH_ARTIFACTS_20260703`

Some read-only Agent Host completions produced generic completion artifacts only. The evidence-bearing all-server matrix for this sweep is `NETWORK_REACHABILITY_MATRIX.md`.

## Example Observed Reasons

- `missing_capability` for review tasks targeted to logical workers without review capability.
- `node_not_allowed` for candidates outside task envelope.
- `node_draining` for drained target.
- `missing_runner_capability` where runner capability is absent.

Deployment check passed against `http://10.99.0.10:9101/v1/tasks/queue/diagnostics`.
