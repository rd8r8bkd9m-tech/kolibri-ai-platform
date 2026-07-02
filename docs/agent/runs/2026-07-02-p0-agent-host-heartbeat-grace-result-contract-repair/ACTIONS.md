# Actions

Completed actions:

- Inspected the existing branch
  `p0/agent-host-heartbeat-grace-2026-07-02`.
- Preserved the existing heartbeat grace implementation and CLI/env setting:
  `--heartbeat-grace`, `KOLIBRI_HEARTBEAT_GRACE_SECONDS`, and
  `KOLIBRI_HEARTBEAT_GRACE`.
- Added `LeaseHeartbeatFailed` in `ops/agent_host.py`.
- Changed heartbeat grace expiry to raise `LeaseHeartbeatFailed` instead of
  `RuntimeError`.
- Updated `run_task` failure serialization so this condition produces:
  - result `status=blocked`
  - result `blocked_reason=lease_heartbeat_failed`
  - fail payload `error_type=lease_heartbeat_failed`
  - heartbeat outage/grace metadata in `result.json`
- Added regression tests in `tests/test_agent_host_runner_contract.py`.

Explicit non-actions:

- Did not edit `ops/factory_control.py`.
- Did not run runtime canaries.
- Did not restart services or mutate live Control Plane state.
