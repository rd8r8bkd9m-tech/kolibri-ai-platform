# ACTIONS

- Updated `backend/factory_status.py` to enrich `/api/factory/status` with wallboard sections:
  - normalized tasks and task state counts;
  - blockers with repair text;
  - PR status records;
  - log/event rows;
  - recent run artifact summaries;
  - server health cards.
- Updated `backend/main.py` 503 fallback so the wallboard still shows an actionable blocker when the Control Plane API is unreachable.
- Rebuilt `frontend/src/App.jsx` cluster tab into `Пульт Home`, a Russian live wallboard for agents, tasks, health, blockers, PRs, logs, and artifacts.
- Added responsive wallboard styles in `frontend/src/App.css`.
- Added contract tests in `tests/test_factory_status.py`.
- Added `scripts/deploy-home-wallboard.sh` with deploy and rollback modes.

