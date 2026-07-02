# Result

Status: `completed`

The Agent Host heartbeat grace result contract is repaired.

Behavior after this change:

- A first task heartbeat must still succeed before the child command starts.
- After at least one successful task heartbeat, transient heartbeat failures are
  tolerated within the configured grace window.
- When the grace window expires, the child process is terminated and the task is
  reported as structured blocked:
  - `error_type=lease_heartbeat_failed`
  - `status=blocked`
  - `blocked_reason=lease_heartbeat_failed`
- The result includes `heartbeat_outage_seconds` and
  `heartbeat_grace_seconds` for diagnosis.

Changed files:

- `ops/agent_host.py`
- `tests/test_agent_host_runner_contract.py`
- `docs/agent/runs/2026-07-02-p0-agent-host-heartbeat-grace-result-contract-repair/PLAN.md`
- `docs/agent/runs/2026-07-02-p0-agent-host-heartbeat-grace-result-contract-repair/ACTIONS.md`
- `docs/agent/runs/2026-07-02-p0-agent-host-heartbeat-grace-result-contract-repair/TESTS.md`
- `docs/agent/runs/2026-07-02-p0-agent-host-heartbeat-grace-result-contract-repair/RESULT.md`
- `docs/agent/runs/2026-07-02-p0-agent-host-heartbeat-grace-result-contract-repair/NEXT.md`

Verification:

- `python3 -m pytest -q tests/test_agent_host_runner_contract.py`
- `git diff --check`

Guardrails honored:

- `ops/factory_control.py` was not touched.
- Runtime canaries were not run.
