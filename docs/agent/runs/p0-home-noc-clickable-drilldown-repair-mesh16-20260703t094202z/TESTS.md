# TESTS

Passed:

- `npx -y node@20 ./node_modules/vite/bin/vite.js build`
  - Result: passed.
  - Note: repo dependencies require Node 20.19+; host default Node is 18.19.1, so the build was run with an ephemeral Node 20 runner.

- `/tmp/home-noc-mesh16-venv/bin/python -m pytest tests/test_factory_status.py -q`
  - Result: `4 passed in 0.18s`.
  - Note: used a temporary virtualenv because system Python is PEP 668 managed.

- Browser click verification against Vite dev server at `http://127.0.0.1:5173/` with Playwright and mocked `/api/factory/status`.
  - Clicked fleet/server KPI `Fleet Total`; confirmed URL included `noc=servers` and `filter=problems`.
  - Clicked `Agents`; confirmed URL included `noc=agents` and `filter=agents`.
  - Clicked queue KPI `Queue Pressure`; confirmed URL included `noc=queues` and `target=factory-queue`.
  - Clicked active task row `P0_BUILD`; confirmed URL included `noc=tasks` and `target=P0_BUILD`.
  - Clicked problem server row `stale-worker`; confirmed URL included `noc=servers`, `target=stale-worker`, and `q=stale-worker`.
  - Confirmed `Server NOC Home` remained visible after fleet and problem drilldowns.

Blocked/not passed:

- `npm run lint`
  - Result: blocked by branch setup, not by this change.
  - Error: ESLint 10 requires `eslint.config.(js|mjs|cjs)`, but this branch does not contain an ESLint config file.

Environment notes:

- Initial `npm run build` under host Node 18.19.1 failed because Vite 8 requires Node 20.19+ or 22.12+.
- Temporary ignored dependencies were installed under `frontend/node_modules/` for local verification only.
