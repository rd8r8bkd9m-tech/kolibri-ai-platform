# Agent Start Here

This is the clean Home-first implementation candidate for Kolibri AI OS. The active FastAPI/React/Fabric/Superfactory production line remains an external compatibility source until a signed replacement release passes all gates.

Read first:

1. `AGENTS.md`
2. `.kolibri/LEAD_AGENT_ACCESS_POLICY.md`
3. `docs/SOURCE_OF_TRUTH.md`
4. `docs/PROJECT_MAP.md`
5. `docs/CONTROL_PLANE_AGENT_MODEL.md`
6. `docs/BOOTSTRAP_TRUTH.md`
7. `release/initial-state.md`
8. `docs/HOME_FIRST_IMPLEMENTATION_STATUS.md`
9. `docs/KOLIBRI_OS_V1_CONTRACT_FREEZE.md`
10. `docs/CONTROL_PLANE_HOME_CANONICAL.md`

Rules:

- Do not read, print, or commit `ops/telegram.env` or other secret-like files.
- Do not execute bootstrap/deploy scripts against production without approval.
- Do not discard untracked runtime artifacts unless explicitly asked.
- Worker agents use API contracts, not SSH.
- Keep this branch aligned with the frozen V1 contracts while preserving active runtime and donor worktrees unchanged.
- Do not import SQLite, daemon-thread execution or legacy Control Plane defaults as new authority.
