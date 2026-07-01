# Actions

Task: P0_CANONICAL_RUN_ARTIFACT_CONTRACT_AND_ALIASES_2026_07_01

- Reset the local worktree to the PR #83 branch source `origin/p0/agent-host-runner-contract-hardening-2026-06-30` at `c837e93ee3bf9da3c07b806ebfc003f52b9ad8d5`.
- Added canonical run artifact constants and finalization helpers in `ops/agent_host.py`.
- Added envelope keys for canonical run directories and explicit aliases.
- Made the finalizer append exact canonical run files to `required_artifacts_present` and `required_artifacts_missing`, so missing files block completion and publishing through the existing contract gate.
- Implemented deterministic explicit alias handling: inspect aliases in order, require all five exact files, copy a complete alias into the canonical directory without overwriting existing files, and persist `run-artifact-aliases.json` in the task artifact directory.
- Documented the canonical run artifact contract in `docs/agent/AGENT_RUNNER_CONTRACT.md`.
- Added focused regression tests in `tests/test_agent_host_runner_contract.py`.
- Confirmed `docs/superfactory/00_README.md`, `docs/superfactory/20_ROADMAP.md`, and `docs/superfactory/TASKS.md` were not modified.
