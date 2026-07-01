# Local Diff To Remote Handoff

Status:
- Local implementation stopped: yes.
- Product code changed on Mac: no.
- Local documentation draft changed on Mac: yes, in a separate worktree.
- Local docs draft authority: not authoritative until remote agent validates or
  recreates it on a server branch and GitHub CI confirms it.

API-first subset:
- Exact API-first control fabric docs from `docs/superfactory/` were relayed
  into PR #85 on branch `p0/api-first-full-control-fabric-2026-07-01`.
- GitHub head `9690361f02addeff37771c52fd37878aef455e13` has CI success.
- Remaining local Superfactory docs outside that subset still need remote
  validation before becoming authoritative.

Local draft worktree:
- `/Users/kolibri/.codex/worktrees/superfactory-docs-package`

Local draft branch:
- `codex/superfactory-docs-package-2026-07-01`

Draft content:
- `docs/superfactory/`
- `docs/agent/runs/2026-07-01-p0-create-kolibri-superfactory-documentation-package/`

Required remote action:
- Remote agent must recreate, apply, or validate the Superfactory docs package
  on a clean server branch.
- Remote result must include task ID, branch/PR, tests, artifacts, blockers, and
  next task.

Important owner rule:
- Owner-facing agents must have Russian human display names plus roles.
