# Queue Diagnostics Report

Before this branch, live `/v1/tasks/queue/diagnostics` returned 404.

This branch adds `queue_diagnostics()` and `GET /v1/tasks/queue/diagnostics`.

## Live Snapshot Used

- Queue total after production deploy: 17.
- Leaseable after production deploy: 17.
- Blocked after production deploy: 0.
- Total task IDs: 21964.
- Endpoint latency after bounding state scan: about 0.22s in the live check.

## Example Observed Reasons

- `missing_capability` for review tasks targeted to logical workers without review capability.
- `node_not_allowed` for candidates outside task envelope.
- `node_draining` for drained target.
- `missing_runner_capability` where runner capability is absent.

Deployment check passed against `http://10.99.0.10:9101/v1/tasks/queue/diagnostics`.
