# Result

Implemented the Agent Host non-empty artifact contract in the proper repository worktree.

- `required_artifacts` and `required_outputs` now require an existing non-empty file.
- Empty required artifacts are reported in `required_artifacts_empty` and block completion.
- Empty canonical run artifacts are reported in `canonical_run_artifacts_empty` and also feed `required_artifacts_empty`.
- Relative required artifact resolution keeps the bootstrapped worktree ahead of `artifact_dir`; an empty worktree file is not bypassed by a non-empty artifact-dir fallback.
- `write_result` mirrors manifest-relevant non-empty worktree artifacts into `artifact_dir` before generating `artifact-manifest.json`, including nested canonical paths and flat canonical filenames.
- Added focused regressions in `tests/test_agent_host_runner_contract.py`.
- Added the future Home canary envelope at `docs/agent/dispatcher/envelopes/P0_HOME_AGENT_HOST_NONEMPTY_ARTIFACT_CONTRACT_CANARY_2026_07_03.json`.

Verification passed with `python3` compile checks, JSON validation, and the focused pytest suite. No live runtime patch, service restart, Home deploy, provider lifecycle operation, main push, or force push was performed.
