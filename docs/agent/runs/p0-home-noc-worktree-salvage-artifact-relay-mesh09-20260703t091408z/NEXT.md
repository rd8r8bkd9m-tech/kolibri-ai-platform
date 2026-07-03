# Next

- Open a PR from `p0/home-noc-worktree-salvage-artifact-relay-mesh09-20260703t091408z`.
- Review the NOC Home screen against live `/api/factory/status` data after deployment.
- Keep Node 20 or newer available for frontend builds; this worker's default Node 18 is below the current Vite requirement.
- If the runner still reports missing artifacts, compare its expected paths with:
  - `docs/agent/runs/p0-home-noc-worktree-salvage-artifact-relay-mesh09-20260703t091408z/`
  - `/var/lib/kolibri-agent/logical-workers/mesh-agent-09/artifacts/P0_HOME_NOC_WORKTREE_SALVAGE_ARTIFACT_RELAY_MESH09_20260703T091408Z/P0_HOME_NOC_WORKTREE_SALVAGE_ARTIFACT_RELAY_MESH09_20260703T091408Z-attempt-1/`
