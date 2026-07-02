# PLAN

Task: `P0_AUTOPILOT_EXTRA_43_SKILLS_REGISTRY_MESH_2026_07_02`

Goal: extract skills registry and professional memory tasks from the master
canvas, map them to servers/agents, and prepare a remote sync plan.

Execution context:
- node: `mesh-agent-43`
- agent: `autonomous_engineer`
- worktree:
  `/var/lib/kolibri-agent/logical-workers/mesh-agent-43/worktrees/P0_AUTOPILOT_EXTRA_43_SKILLS_REGISTRY_MESH_2026_07_02/P0_AUTOPILOT_EXTRA_43_SKILLS_REGISTRY_MESH_2026_07_02-attempt-1/repo`
- local Mac product-code execution: none

Steps:
1. Inspect git state and existing dispatcher/run artifact conventions.
2. Extract relevant master canvas sections from
   `docs/superfactory/Kolibri_All_Prompts.md`.
3. Map extracted work to server-side nodes and Russian owner-facing agents.
4. Define a gated remote sync plan that does not install unaudited skills.
5. Produce status, artifacts, blockers, risks, and the next exact task.

Constraints:
- No secrets printed.
- No destructive git commands.
- No force push and no push to `main`.
- No product code changes.
- No server-wide skill install before registry/security decisions exist.

