# P0_AUTOPILOT_EXTRA_22_HIGHLOAD_READINESS_2026_07_02 Plan

Task: probe `hostvds-highload` through API/fallback routes, classify readiness,
capacity, blockers, and the exact repair task.

Execution node:

- Node: `mesh-agent-22`
- Lease owner: `mesh-agent-22:agent-host-mesh-agent-22`
- Agent: `Роман - Highload Readiness`
- Worktree: `/var/lib/kolibri-agent/logical-workers/mesh-agent-22/worktrees/P0_AUTOPILOT_EXTRA_22_HIGHLOAD_READINESS_2026_07_02/P0_AUTOPILOT_EXTRA_22_HIGHLOAD_READINESS_2026_07_02-attempt-1/repo`

Plan:

1. Confirm remote/server-side execution lease for the assigned worker.
2. Probe the control plane health and available node API surfaces.
3. Probe canonical and fallback route endpoints for `hostvds-highload`/`highload`/`mesh-highload`.
4. Inspect current highload node cards and prior highload tasks without printing secrets.
5. Classify readiness, live capacity, blockers, fallback candidates, and the next exact repair task.

