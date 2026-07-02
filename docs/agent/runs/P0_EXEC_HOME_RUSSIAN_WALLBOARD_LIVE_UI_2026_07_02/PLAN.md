# PLAN

Task: P0_EXEC_HOME_RUSSIAN_WALLBOARD_LIVE_UI_2026_07_02

1. Extend the existing live factory status API instead of adding a separate dashboard backend.
2. Normalize agents, task states, active tasks, server health, blockers, PRs, logs, and recent run artifacts into one safe payload.
3. Replace the node-only cluster tab with a Russian Home wallboard view.
4. Add a reversible deploy script for Home/main service rollout with backup and rollback command.
5. Verify with backend contract tests and a production frontend build.

