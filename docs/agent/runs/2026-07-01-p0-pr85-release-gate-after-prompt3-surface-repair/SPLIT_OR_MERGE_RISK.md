# Split Or Merge Risk

Release-gate classification: no split required.

Reasons:

- PR #85 is scoped to API-first Fabric docs, Control Plane/Fabric API server surface, dispatch behavior and tests.
- The latest Prompt #3 repair did not introduce frontend, billing, Telegram UX, FormulaLM training, model downloads, credential rotation, deployment or service restart work.
- Admin endpoints are deny-by-default stubs, so privileged behavior is not silently enabled.
- Model endpoints are safe blocked stubs/catalog, so provider calls or secret handling are not introduced.

Merge risk before whitespace fix:

- `git diff --check origin/main...HEAD` fails on doc-only EOF whitespace in `docs/superfactory/*.md`.
- This is small and should be repaired in PR #85 before mark-ready/merge.

Post-merge/runtime risk:

- Live Redis-backed endpoint behavior should be canaried after deploy.
- PR #91 remains useful for MIMO runner/auth rollout, but it is not a blocker for PR #85 endpoint-surface merge after the minor docs fix.
