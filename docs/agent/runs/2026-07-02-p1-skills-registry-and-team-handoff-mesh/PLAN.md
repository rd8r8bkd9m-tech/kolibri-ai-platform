# PLAN

Task: `P1_SKILLS_REGISTRY_AND_TEAM_HANDOFF_MESH_2026_07_02`

Goal: start a docs-only skills registry and Russian-name agent handoff protocol
after P0 lanes are visible, without mixing product features.

Plan:

1. Verify P0 visibility from existing dispatcher queue and run artifacts.
2. Create reusable docs-only contracts for the skills registry and handoff
   protocol.
3. Create dispatchable P1 task matrix with status, lease owner, artifacts,
   blockers and next action.
4. Add a Control Plane envelope for server-side docs-only execution.
5. Update dispatcher queue and log so the next agent can continue from an
   artifact-backed state.
6. Verify exact files, JSON validity and docs diff hygiene.

Scope guard:

- Allowed: `docs/agent/dispatcher/**`, `docs/agent/runs/**`,
  `docs/agent/intelligence/**`.
- Forbidden: product code, runtime service changes, live deploys, pushes to
  `main`, force pushes and destructive git.

