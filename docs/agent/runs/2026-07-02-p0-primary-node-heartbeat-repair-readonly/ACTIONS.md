# Actions

- Confirmed execution on server host `kolibri`, Linux, from the Agent Host
  worktree for `mesh-agent-12`.
- Confirmed `kolibri-factory-control.service` is `active/running` with PID
  `3588876`, started `2026-07-01 21:49:49 UTC`.
- Confirmed Factory Control is bound to `10.99.0.10:9101`; loopback
  `127.0.0.1:9101` refused connections.
- Probed read-only routes:
  - `GET http://10.99.0.10:9101/v1/health`
  - `GET http://10.99.0.10:9101/v1/fabric/health`
  - `GET http://10.99.0.10:9101/v1/nodes`
  - `GET http://10.99.0.10:9101/v1/fleet/route?target_node=primary-candidate`
  - `GET http://10.99.0.10:9101/v1/fleet/route?target_node=primary-candidate&required_capability=generic_implementation`
  - `GET http://10.99.0.10:9101/v1/tasks/P0_PRIMARY_NODE_HEARTBEAT_REPAIR_READONLY_2026_07_02`
  - `GET http://10.99.0.10:9101/v1/tasks/P0_30MIN_12AGENT_05B_RUNNER_CONTRACT_STEWARD_FALLBACK_2026_07_02`
- Read sanitized `kolibri-factory-control.service` unit metadata, listener
  state, process command, and journal lines. No environment files or secrets
  were printed.
- Patched `ops/factory_control.py` so `fabric_route()` applies
  `classify_node_freshness()` to registered nodes that have `heartbeat_at`
  before route selection.
- Added `tests/test_fabric_control.py` coverage for a stale
  `primary-candidate` record that still reports `health: online`.
- No restart, push, force push, or destructive git command was performed.

