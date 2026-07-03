# Actions

- Created this canonical run artifact set at the exact requested path before code changes.
- Updated `ops/agent_host.py` so required artifacts are classified with non-empty `test -s` semantics.
- Added `required_artifacts_empty` and `canonical_run_artifacts_empty` reporting for empty files.
- Preserved worktree-first resolution for relative required artifact paths.
- Mirrored non-empty required/canonical worktree artifacts into `artifact_dir` before `artifact-manifest.json` is written, including both nested canonical paths and flat canonical filenames.
- Added a future Home canary envelope at `docs/agent/dispatcher/envelopes/P0_HOME_AGENT_HOST_NONEMPTY_ARTIFACT_CONTRACT_CANARY_2026_07_03.json`; it is a handoff document only and forbids restart/deploy.
