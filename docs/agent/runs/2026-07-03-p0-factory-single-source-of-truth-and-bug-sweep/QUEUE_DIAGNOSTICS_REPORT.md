# Queue Diagnostics Report

Before this branch, live `/v1/tasks/queue/diagnostics` returned 404.

This branch adds `queue_diagnostics()` and `GET /v1/tasks/queue/diagnostics`.

## Live Snapshot Used

- Queue total from live summary endpoint: 18.
- Blocked from live diagnostics embedded in task summary: 9.
- Total task IDs: 21964.

## Example Observed Reasons

- `missing_capability` for review tasks targeted to logical workers without review capability.
- `node_not_allowed` for candidates outside task envelope.
- `node_draining` for drained target.
- `missing_runner_capability` where runner capability is absent.

After deployment, this report must be regenerated from the new endpoint.

