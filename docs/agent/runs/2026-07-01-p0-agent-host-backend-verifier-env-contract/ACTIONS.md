# Backend Verifier Env Contract Actions

Task ID: `P0_AGENT_HOST_BACKEND_VERIFIER_ENV_CONTRACT_2026_07_01`

Actions:

- Added explicit backend Python verification env envelope keys:
  `backend_python_verification_env`, `backend_test_environment`, and
  `backend_verification_environment`.
- Added backend env setup helpers that create a temporary venv, install explicit
  requirements files and package lists, rewrite `python`/`python3`/`pytest`
  verifier commands to the env interpreter, and clean up by default.
- Rejected backend env paths under the worktree so temporary dependency trees
  cannot become committed files.
- Added structured setup-failure classification through
  `backend_test_environment_failed`.
- Wired PR review test execution to use the declared backend env only when the
  envelope opts in; the existing default pytest venv path remains unchanged.
- Added focused runner contract tests for raw-Python dependency failure,
  backend-env verifier success, cleanup/exclusion, and setup-failure blockers.
- Documented the contract in `docs/agent/AGENT_RUNNER_CONTRACT.md`.
- Added `.gitignore` guards for standard backend test env directory names.
