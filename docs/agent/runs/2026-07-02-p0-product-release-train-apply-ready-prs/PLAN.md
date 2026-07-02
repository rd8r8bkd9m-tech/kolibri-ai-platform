# Plan

Task: `P0_PRODUCT_RELEASE_TRAIN_APPLY_READY_PRS_2026_07_02`

1. Recheck the live GitHub PR queue through the GitHub connector.
2. Identify mergeable draft PRs with successful current-head Kolibri CI.
3. Move verified PRs toward owner review without marking ready, approving, merging, closing, force-pushing, or pushing to `main`.
4. Record the release train order, checks evidence, and remaining blockers in source-controlled artifacts.

Guardrails:

- No secrets printed.
- No production deploy or service restart.
- No main mutation.
- No draft-to-ready conversion without explicit owner approval.
