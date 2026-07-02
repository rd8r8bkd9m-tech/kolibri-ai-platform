# Plan

Task id: `P0_AGENT_HOST_HEARTBEAT_GRACE_RESULT_CONTRACT_REPAIR_2026_07_02`

Branch: `p0/agent-host-heartbeat-grace-2026-07-02`

Scope:

- Continue from the existing primary-candidate branch created by
  `P0_AGENT_HOST_HEARTBEAT_GRACE_FOR_CONTROL_PLANE_RESTART_2026_07_02`.
- Keep the scoped Agent Host heartbeat grace behavior.
- Repair the result/error contract so grace expiry is structured as
  `lease_heartbeat_failed`, not generic `runtime_error`.
- Do not edit `ops/factory_control.py`.
- Do not run runtime canaries.

Implementation plan:

1. Add a dedicated Agent Host exception for task lease heartbeat expiry.
2. Preserve transient heartbeat grace handling after a successful heartbeat.
3. Map grace expiry in `run_task` to a blocked result with
   `blocked_reason=lease_heartbeat_failed` and `error_type=lease_heartbeat_failed`.
4. Add focused tests for direct expiry and full task failure serialization.
5. Record focused verification and exact handoff artifacts.
