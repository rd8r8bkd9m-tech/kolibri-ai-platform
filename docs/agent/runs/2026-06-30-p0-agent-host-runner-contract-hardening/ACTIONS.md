# Actions

- Added `CONTRACT_RESULT_FIELDS` and contract helper functions to
  `ops/agent_host.py`.
- Added envelope constraint parsing with support for top-level flags and nested
  `constraints`.
- Added required artifact verification for `required_outputs` and
  `required_artifacts`.
- Added strict `write_scope` checking with exact path, directory prefix, and
  simple glob support.
- Added read-only, documentation-only, and product-code modification guards.
- Added no-push enforcement for `git_push_forbidden`, `no_push`, and
  `read_only`.
- Replaced direct implementation-runner `git push` calls with `AgentHost.git_push`.
- Added `unsupported_task_result` and `AgentHost.unsupported_task_reason`.
- Updated `run_task` to call `/complete` only after the runner contract
  finalizer confirms completion is allowed.
- Updated runner methods to persist contract-normalized `result.json` files.
- Added focused tests in `tests/test_agent_host_runner_contract.py`.
- Added `run_task` integration tests proving blocked tasks call `/fail`, not
  `/complete`.
- Added this run report directory and `docs/agent/AGENT_RUNNER_CONTRACT.md`.
- Added Superfactory Prompt 19 addendum docs without widening implementation
  scope:
  - `docs/superfactory/00_README.md`
  - `docs/superfactory/20_ROADMAP.md`
  - `docs/superfactory/TASKS.md`
  - `docs/agent/runs/2026-06-30-p0-agent-host-runner-contract-hardening/SUPERFACTORY_ADDENDUM.md`
