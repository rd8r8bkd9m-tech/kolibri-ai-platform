# Plan

Task id: `P0_PRIMARY_NODE_HEARTBEAT_REPAIR_READONLY_2026_07_02`

Node: `kolibri`

Execution host: server Agent Host worktree
`/var/lib/kolibri-agent/logical-workers/mesh-agent-12/worktrees/P0_PRIMARY_NODE_HEARTBEAT_REPAIR_READONLY_2026_07_02/P0_PRIMARY_NODE_HEARTBEAT_REPAIR_READONLY_2026_07_02-attempt-1/repo`.

1. Verify the task is running on a server Agent Host, not a local Mac.
2. Probe Factory Control read-only without printing secrets.
3. Compare `primary-candidate` node heartbeat freshness with active task heartbeat freshness.
4. Patch the route selection contract so stale `online` node metadata cannot bypass heartbeat freshness.
5. Add regression tests and record artifacts.
6. Do not restart live services in this task.

