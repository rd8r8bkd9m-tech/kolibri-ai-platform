# Verification

- `python3 -m json.tool docs/agent/dispatcher/envelopes/P0_AUTOPILOT_CANONICAL_20_SERVER_READINESS_MATRIX_2026_07_02.json >/dev/null`
- `python3 -m json.tool docs/agent/dispatcher/envelopes/P0_AUTOPILOT_50PCT_CAPACITY_GOVERNOR_2026_07_02.json >/dev/null`
- `python3 -m json.tool docs/agent/dispatcher/envelopes/P0_AUTOPILOT_GUARDIAN_CONTROL_PLANE_STEWARD_2026_07_02.json >/dev/null`
- `python3 -m json.tool docs/agent/dispatcher/envelopes/P0_AUTOPILOT_GUARDIAN_PR105_RELEASE_STEWARD_2026_07_02.json >/dev/null`
- `python3 -m json.tool docs/agent/dispatcher/envelopes/P0_AUTOPILOT_GUARDIAN_RUNNER_CONTRACT_STEWARD_2026_07_02.json >/dev/null`
- `python3 ops/kolibri-dispatch submit --file <envelope>` for all five child task envelopes.
- `python3 ops/kolibri-dispatch status <task_id>` for parent and five child tasks.
- `python3 -m json.tool docs/agent/runs/2026-07-02-p0-autopilot-2h-50pct-launch-orchestrator/status-*.json >/dev/null` through the shell validation loop.

Result: Control Plane accepted all five child task envelopes after adding the required `branch`, `base_ref`, and `verification_commands` fields.
