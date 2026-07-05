# Agent Start Here

This is the active FastAPI/React/Fabric/Superfactory branch for KolibriAI Platform.

Read first:

1. `AGENTS.md`
2. `.kolibri/LEAD_AGENT_ACCESS_POLICY.md`
3. `docs/SOURCE_OF_TRUTH.md`
4. `docs/PROJECT_MAP.md`
5. `docs/CONTROL_PLANE_AGENT_MODEL.md`
6. `docs/BOOTSTRAP_TRUTH.md`
7. `release/initial-state.md`

Rules:

- Do not read, print, or commit `ops/telegram.env` or other secret-like files.
- Do not execute bootstrap/deploy scripts against production without approval.
- Do not discard untracked runtime artifacts unless explicitly asked.
- Worker agents use API contracts, not SSH.
- Keep this branch aligned with Calibri V1 source of truth while preserving active runtime behavior.
