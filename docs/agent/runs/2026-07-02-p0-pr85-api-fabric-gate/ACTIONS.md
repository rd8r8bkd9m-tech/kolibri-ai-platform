# PR85 API Fabric Gate Actions

Remote execution:

- Repository path: `/var/lib/kolibri-agent/logical-workers/mesh-agent-38/worktrees/P0_AUTOPILOT_EXTRA_38_PR85_API_FABRIC_GATE_2026_07_02/P0_AUTOPILOT_EXTRA_38_PR85_API_FABRIC_GATE_2026_07_02-attempt-1/repo`
- Node: `kolibri`
- Branch: `agent/P0_AUTOPILOT_EXTRA_38_PR85_API_FABRIC_GATE_2026_07_02/generic`
- Local HEAD before docs artifact: `f7ac32c70406432a52752ca45d87e35d9f1facd3`

Git/ref checks:

- `git fetch origin --prune`
- `git ls-remote origin refs/pull/85/head refs/pull/91/head refs/heads/p0/api-first-full-control-fabric-2026-07-01 refs/heads/p0/mimo-runner-output-auth-contract-repair-2026-07-01 refs/heads/main`
- `git log --oneline --decorate --grep='(#91)' --all --max-count=20`
- `git log --oneline --decorate --max-count=10 origin/p0/api-first-full-control-fabric-2026-07-01..origin/main`

Current refs observed:

- `main`: `f7ac32c70406432a52752ca45d87e35d9f1facd3`
- PR #85 branch/ref: `45388df7e66031f5256489de5dc871b3d71ad502`
- PR #91 branch/ref: `465bd7e7272673d569bf4fa47b20e0fb4ba349a6`

Merged-main evidence:

- Current `main` contains PR #85 merge commit `1b08c43 p0: finalize API-first full-control Fabric (#85)`.
- Current `main` contains PR #91 merge commit `9000973 p0: fix MIMO runner output and auth classification (#91)`.
- The old PR #85 and PR #91 branch heads still exist remotely but are not ancestors of current `main`; they are stale branch heads and should not be merged as-is.

Product-code action:

- None. This run modified only release-gate documentation artifacts.
