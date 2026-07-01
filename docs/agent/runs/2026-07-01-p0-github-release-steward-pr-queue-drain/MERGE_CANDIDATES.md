# Merge Candidates

Candidates after rebase/recheck:

- PR #84: docs-only Superfactory master canvas.
- PR #88: docs-only dispatcher ledger.
- PR #65: GoMesh rollout verification runbook, pending base branch strategy.

Rules before any merge:

- Rebase or update against current `main` after PR #95.
- Run `git diff --check`.
- Run a narrow secret-pattern scan over changed docs.
- Re-check GitHub CI and mergeability immediately before owner-approved merge.
