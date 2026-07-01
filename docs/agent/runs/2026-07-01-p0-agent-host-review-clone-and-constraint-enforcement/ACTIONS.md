# Agent Host Review Clone And Constraint Enforcement Actions

Task ID: `P0_AGENT_HOST_REVIEW_CLONE_AND_CONSTRAINT_ENFORCEMENT_2026_07_01`

## Actions

- Fast-forwarded the local PR #83 branch from `6d0317c52a9694448ee2c352dc196ce7a27b9487` to required head `9bebf6cdba32a6886b6343f3701add3e85d18e41`.
- Added Agent Host permission sanitization so no-push/read-only envelopes cannot retain `git_push` or a `full_autonomy` permission pack.
- Preserved the existing publish-after-contract-verification gate and added a central-branch no-push regression test.
- Added review clone/auth failure classification for permission denied, repository access, prompt, and hostname failures.
- Ensured review clone/auth failures are reported with `error_type: review_clone_auth_failed`, `retry: false`, and a `result.json` at `result_reference`.
- Updated the Agent Host runner contract documentation with permission and clone/auth fallback behavior.

## Changed Files

- `ops/agent_host.py`
- `tests/test_agent_host_runner_contract.py`
- `docs/agent/AGENT_RUNNER_CONTRACT.md`
- `docs/agent/runs/2026-07-01-p0-agent-host-review-clone-and-constraint-enforcement/PLAN.md`
- `docs/agent/runs/2026-07-01-p0-agent-host-review-clone-and-constraint-enforcement/ACTIONS.md`
- `docs/agent/runs/2026-07-01-p0-agent-host-review-clone-and-constraint-enforcement/TESTS.md`
- `docs/agent/runs/2026-07-01-p0-agent-host-review-clone-and-constraint-enforcement/RESULT.md`
- `docs/agent/runs/2026-07-01-p0-agent-host-review-clone-and-constraint-enforcement/NEXT.md`
- `docs/agent/runs/2026-07-01-p0-agent-host-review-clone-and-constraint-enforcement/REMOTE_RESULT.json`
