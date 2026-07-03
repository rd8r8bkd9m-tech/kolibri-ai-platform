# Next

- Deploy the branch to the Control Plane sidecar and reload the service.
- Verify live `/v1/nodes` against active P0 task ids for `main`, `mesh-agent-04`, `mesh-agent-05`, `mesh-agent-06`, and `primary-candidate`.
- Confirm Home NOC `/api/factory/status` shows active workers as online/fresh while still exposing stale node-heartbeat evidence.
- Follow up separately if Agent Host should also emit node heartbeats during long-running commands; this fix keeps the operator view accurate without changing runner execution behavior.
