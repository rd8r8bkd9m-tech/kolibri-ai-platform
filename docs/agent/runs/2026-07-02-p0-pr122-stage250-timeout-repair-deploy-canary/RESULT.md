# Result

Status: runtime deploy/canary completed on healthy local node `kolibri` / `primary-candidate`.

Result reference:

- `docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/RESULT.md`
- Runtime backup: `/opt/kolibri-ai-platform/.rollback/20260704T053602Z-stage250-lease-timeout`
- Runtime canary report: `docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/RUNTIME_CANARY_REPORT.md`

Deployment result:

- Runtime file patched: `/opt/kolibri-ai-platform/ops/factory_control.py`
- Restarted service: `kolibri-factory-control.service`
- Final service state: `active`
- Final service PID observed: `3671467`
- Final service tasks observed: `1`
- Final memory observed: `20.2M`
- Rollback applied: no

Canary result:

- Routes `/health`, `/v1/health`, `/v1/fabric/health`, `/v1/fabric/routes`, `/v1/fleet/nodes`, and `/v1/models` passed.
- 250 lease polls completed with HTTP 200.
- Lease 5xx count: `0`.
- Client timeout count after batched reaper patch: `0`.
- Queued tasks leased by canary: `0`.

Important finding:

- The first probe against `10.99.0.2:9101` hit a different/main endpoint and returned 250/250 HTTP 204 legacy lease responses. The deploy/canary target for this task was the local healthy node endpoint `10.99.0.10:9101`.
- A first local 250-poll canary after bounded server deploy returned zero 5xx but showed 35 client timeouts. The residual blocker was the live runtime's unbounded `requeue_expired_leases()` call on every lease request.
- The residual timeout was repaired by adding the lock-gated, batched reaper path before the final passing canary.

Changed files in this repo:

- `docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/PLAN.md`
- `docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/ACTIONS.md`
- `docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/TESTS.md`
- `docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/RESULT.md`
- `docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/NEXT.md`
- `docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/RUNTIME_CANARY_REPORT.md`
- `docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/ROLLBACK_RECORD.md`

Commit/PR evidence:

- Branch pushed: `codex/pr122-lease-stage250-backpressure-repair`.
- PR evidence: GitHub connector verified PR #125 changed-file list includes all seven required run artifacts plus `ops/factory_control.py` and `tests/test_factory_capacity_controls.py`.
- PR URL: `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/125`.
- Final pushed commit is reported in the completion response after this artifact update is committed.
