# P0 GitHub PR Matrix Markdown Relay Plan

Run: `P0_GITHUB_PR_MATRIX_MARKDOWN_RELAY_MESH15_20260703T093604Z`

Mode: remote-only narrow artifact relay.

## Scope

- Preserve the useful findings from `P0_GITHUB_PR_MATRIX_ARTIFACT_RELAY_MESH14_20260703T092953Z`.
- Produce exactly the required markdown artifacts for this run directory:
  - `PLAN.md`
  - `ACTIONS.md`
  - `TESTS.md`
  - `RESULT.md`
  - `NEXT.md`
- Include a PR matrix with PR URLs/IDs, requested branch, resolved branch/head SHA, status, mergeability, and the revenue/free-VPS blocker.
- Avoid broad GitHub rework, main pushes, merges, force pushes, fake PR URLs, and secret disclosure.

## Inputs

- Previous worktree: `/var/lib/kolibri-agent/logical-workers/mesh-agent-14/worktrees/P0_GITHUB_PR_MATRIX_ARTIFACT_RELAY_MESH14_20260703T092953Z/P0_GITHUB_PR_MATRIX_ARTIFACT_RELAY_MESH14_20260703T092953Z-attempt-1/repo`
- Previous result: `/var/lib/kolibri-agent/logical-workers/mesh-agent-14/artifacts/P0_GITHUB_PR_MATRIX_ARTIFACT_RELAY_MESH14_20260703T092953Z/P0_GITHUB_PR_MATRIX_ARTIFACT_RELAY_MESH14_20260703T092953Z-attempt-1/result.json`
- Previous human matrix: `/var/lib/kolibri-agent/logical-workers/mesh-agent-14/artifacts/P0_GITHUB_PR_MATRIX_ARTIFACT_RELAY_MESH14_20260703T092953Z/P0_GITHUB_PR_MATRIX_ARTIFACT_RELAY_MESH14_20260703T092953Z-attempt-1/PR_MATRIX.md`

## Guardrails

- No direct push to `main`.
- No merge.
- No force push.
- No fabricated PR URL for the missing revenue/free-VPS head.
- No secrets in artifacts or logs.
