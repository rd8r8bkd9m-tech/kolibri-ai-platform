# Plan

Task id: `P0_UIAP_RAG_NODE_TOOLING_LIGHT_REPAIR_2026_07_02`

Scope: classify and lightly repair `uiap` readiness for RAG/knowledge tasks from
the server Agent Host execution environment, without heavy builds, secret
printing, destructive git operations, force pushes, or pushes to `main`.

Execution rules:

- Run only non-destructive probes for host identity, disk, git, Codex/tooling,
  and Agent Host service state.
- Use repo-local contract tests and preflight scripts only.
- Do not install packages unless a safe, official, required package gap is found.
- Prefer docs-only repair when the runtime state is already usable and the main
  missing output is canonical artifact evidence.

Required artifacts:

- `PLAN.md`
- `ACTIONS.md`
- `TESTS.md`
- `NODE_TOOLING_MATRIX.md`
- `RESULT.md`
- `NEXT.md`
- `REMOTE_RESULT.json`

