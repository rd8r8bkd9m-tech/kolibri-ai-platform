# Result

Status: completed locally, ready for PR review.

Implemented behavior:

- Runner results are normalized to the contract fields before they are written
  and before Control Plane completion.
- `/complete` is no longer called when required artifacts are missing, write
  scope is violated, read-only/product-code constraints are violated, a
  forbidden push was attempted, or task kind/capability is unsupported.
- Unsupported task kinds return a structured `blocked` result and are sent to
  `/fail` with `error_type: runner_contract_blocked`.
- Missing required artifacts are verified through the real `run_task` path and
  are sent to `/fail`, not `/complete`.
- Implementation runners skip `git push` when push is forbidden and report
  `push_attempted: false`, `push_blocked: true`, and a reason.
- The P0 integration audit artifact-path drift case is covered by a regression
  test.

Files changed:

- `ops/agent_host.py`
- `tests/test_agent_host_runner_contract.py`
- `docs/agent/AGENT_RUNNER_CONTRACT.md`
- `docs/agent/runs/2026-06-30-p0-agent-host-runner-contract-hardening/PLAN.md`
- `docs/agent/runs/2026-06-30-p0-agent-host-runner-contract-hardening/ACTIONS.md`
- `docs/agent/runs/2026-06-30-p0-agent-host-runner-contract-hardening/TESTS.md`
- `docs/agent/runs/2026-06-30-p0-agent-host-runner-contract-hardening/RESULT.md`
- `docs/agent/runs/2026-06-30-p0-agent-host-runner-contract-hardening/NEXT.md`

Blocked items:

- None for this local branch.
- Server rollout and Control Plane rerun are intentionally left for the next
  supervised task.
