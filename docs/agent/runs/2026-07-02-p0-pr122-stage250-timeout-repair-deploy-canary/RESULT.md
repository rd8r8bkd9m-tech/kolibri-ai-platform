# Result

Status: `passed_runtime_canary`

Summary:

- PR #125 head and merge refs were fetched and recorded.
- Live Factory Control on `10.99.0.2:9101` already contained the PR #125 lease fast-path deployment markers from the prior runtime attempt.
- Existing rollback backup material was verified.
- Bounded synthetic lease pressure stages 20, 50, 100, and 250 were run against the live `/v1/tasks/lease` endpoint.
- No task was claimed by the synthetic canary.
- No full worker wave, MIMO wave, FormulaLM wave, qjns/uiap targeting, Telegram mutation, task cancellation, or original-task mutation was performed.
- Post-canary health and required Fabric routes returned HTTP 200.
- Rollback was not needed.

CI/check status:

Fresh GitHub check-run status could not be verified from this node because local `gh` is unauthenticated and unauthenticated GitHub REST returns `404` for this private repository. The result is grounded in fetched PR refs, GitHub connector commit evidence, PR #125 run artifact test evidence, local focused tests, and live runtime canary evidence.

Node:

- Executed on Control Plane lease owner `main:agent-host-main`.
- `main` is in `allowed_nodes` and was healthy/fresh.
- The envelope also listed `main` in `avoid_nodes`; this is recorded in `ACTIONS.md`. No requeue/reassignment was performed because the rebroadcast required avoiding mutation of the original task and current lease.

Checks:

- `python3 -m py_compile ops/factory_control.py ops/agent_host.py` passed.
- `python3 -m py_compile /usr/local/bin/kolibri-factory-control` passed.
- `python3 -m pytest -q tests/test_factory_runtime.py tests/test_factory_runtime_queue_contracts.py tests/test_agent_host_runner_contract.py` -> `42 passed in 97.17s`.
- `git ls-remote` verified PR #125 head and merge refs.
- Bounded stage canary: 420 total synthetic lease requests, `204` for all, 0 task claims, 0 errors, 0 5xx.
- Post-canary route matrix: `/health`, `/v1/health`, `/v1/fabric/health`, `/v1/fabric/routes`, `/v1/fleet/nodes`, `/v1/models` all HTTP 200.
- Journal scan found no canary-window `BrokenPipe`, `Too many open files`, `Traceback`, `ERROR`, `Errno 24`, or explicit ` 500 ` lines.

Result reference:

`docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/RESULT.md`

Changed files:

- `docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/PLAN.md`
- `docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/ACTIONS.md`
- `docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/TESTS.md`
- `docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/RESULT.md`
- `docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/NEXT.md`
- `docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/RUNTIME_CANARY_REPORT.md`
- `docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/ROLLBACK_RECORD.md`

