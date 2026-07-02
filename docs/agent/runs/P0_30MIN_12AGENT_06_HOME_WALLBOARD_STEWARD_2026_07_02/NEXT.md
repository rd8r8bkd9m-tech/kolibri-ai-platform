# Next

Exact next tasks:

1. `P0_FACTORY_CONTROL_TELEGRAM_GATEWAY_OWNER_APPROVED_NO_MUTATION_DIAGNOSTIC_2026_07_02`
   - Goal: classify Telegram gateway ownership/startup safety after Factory Control deploy canary passed.
   - Constraints: no Bot API mutation, no `getUpdates`, no webhook deletion, no service start/restart unless owner-approved and single receiver safety is proven.
   - Required output: exact run artifacts with service state, receiver ownership evidence, no-mutation proof, and next live action.

2. `P0_HOME_FACTORY_TERMINAL_UI_RU_2026_07_01` rerun or artifact repair
   - Goal: create or prove owner-visible Russian tmux wallboard on `home` or documented fallback.
   - Required session: `kolibri-factory-screen` or compatible existing session.
   - Required output: exact attach/view command, live data sources, node/task/repair panels, blockers, and canonical artifacts under `docs/agent/runs/2026-07-01-p0-home-factory-terminal-ui-ru/`.

3. `P0_FACTORY_STATUS_TEST_ENV_REPAIR_2026_07_02`
   - Goal: repair the control-node Python test environment without modifying product code.
   - Required check: rerun `python3 -m pytest -q tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py`.
   - Constraint: use approved venv/system package path; do not bypass PEP 668 in the system Python.

4. `P0_GITHUB_PR_QUEUE_METADATA_TOOLING_REPAIR_2026_07_02`
   - Goal: classify PR queue metadata from a node with approved GitHub tooling/auth.
   - Required check: prove `gh` or GitHub app path works without printing credentials.

Immediate steward recommendation:

- Do not claim the Home wallboard is owner-visible until a Home/fallback task returns the exact tmux attach command and artifacts.
- Do not claim Telegram runtime health until the no-mutation diagnostic completes.
- Do claim Factory Control route health only with the later deploy canary evidence from `2026-07-02-p0-factory-control-post-merge-deploy-canary`.

