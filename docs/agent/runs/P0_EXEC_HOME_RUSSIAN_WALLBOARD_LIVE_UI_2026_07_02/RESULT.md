# RESULT

Implemented execution change.

What now works:

- Home wallboard is available in the frontend as `Пульт Home`.
- `/api/factory/status` now returns a richer safe payload for Russian live operations: agents, freshness, task states, active tasks, server health, blockers, PRs, logs, and recent run artifacts.
- If Control Plane is unreachable, the API returns an actionable wallboard blocker instead of an empty dashboard.
- A scoped deploy helper exists at `scripts/deploy-home-wallboard.sh`.

Rollback:

```bash
scripts/deploy-home-wallboard.sh rollback <backup-dir> kolibri-main /opt/kolibri-ai
```

Deploy:

```bash
scripts/deploy-home-wallboard.sh deploy kolibri-main /opt/kolibri-ai
```

Remaining blocked:

- Live PR/blocker/log sections depend on Control Plane exposing `/v1/prs`, `/v1/blockers`, and `/v1/logs`; when absent, the dashboard shows safe empty states and recent run artifacts.
- This workspace cannot run plain `npm run build` with system Node 18. Use Node 20.19+ on the deployment host or the verified `npx -p node@20` command.

Artifacts:

- `docs/agent/runs/P0_EXEC_HOME_RUSSIAN_WALLBOARD_LIVE_UI_2026_07_02/PLAN.md`
- `docs/agent/runs/P0_EXEC_HOME_RUSSIAN_WALLBOARD_LIVE_UI_2026_07_02/ACTIONS.md`
- `docs/agent/runs/P0_EXEC_HOME_RUSSIAN_WALLBOARD_LIVE_UI_2026_07_02/TESTS.md`
- `docs/agent/runs/P0_EXEC_HOME_RUSSIAN_WALLBOARD_LIVE_UI_2026_07_02/RESULT.md`
- `docs/agent/runs/P0_EXEC_HOME_RUSSIAN_WALLBOARD_LIVE_UI_2026_07_02/NEXT.md`

