# Plan

Task: `P0_CANONICAL_20_SERVER_READINESS_MATRIX_2026_07_02`
Lease owner: `autonomous_engineer`
Execution host: `kolibri` Linux server via Agent Host worktree, not Mac.

1. Verify execution context is a server Agent Host worktree.
2. Read existing fleet, freshness, deploy, and repair artifacts for prior evidence.
3. Probe only read-only local/server surfaces: Control Plane health, Control Plane fleet nodes, Git remote fetch visibility, and runner binary presence.
4. Create canonical 20-server readiness matrix with one row per logical server identity.
5. Record blockers, safe 50 percent capacity slots, next repair action, verification commands, and wrapper-readable task result artifacts.

No production mutation, secret read, push, force push, or destructive git action is planned.
