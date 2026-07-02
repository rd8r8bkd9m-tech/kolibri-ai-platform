# RESULT

Status: implemented and locally verified for the changed runtime surface.

What now works:

- Expired `leased`, `running`, and `review` tasks are reconciled through status reads and lease polling.
- Tasks with retry budget remaining are cleared of stale lease ownership and returned to `queued`.
- Tasks with exhausted retry budget are moved to `dead_letter`.
- Requeue and dead-letter insertion are duplicate guarded.
- Runtime status payloads expose `runtime_reconciliation` and `dead_letter` for operator visibility.
- Each lease-expiry decision records a bounded `runtime_events` entry on the task.

Changed files:

- `ops/factory_control.py`
- `tests/test_factory_runtime_queue_contracts.py`
- `docs/agent/runs/P0_EXEC_QUEUE_REQUEUE_DEADLETTER_RUNTIME_2026_07_02/PLAN.md`
- `docs/agent/runs/P0_EXEC_QUEUE_REQUEUE_DEADLETTER_RUNTIME_2026_07_02/ACTIONS.md`
- `docs/agent/runs/P0_EXEC_QUEUE_REQUEUE_DEADLETTER_RUNTIME_2026_07_02/TESTS.md`
- `docs/agent/runs/P0_EXEC_QUEUE_REQUEUE_DEADLETTER_RUNTIME_2026_07_02/RESULT.md`
- `docs/agent/runs/P0_EXEC_QUEUE_REQUEUE_DEADLETTER_RUNTIME_2026_07_02/NEXT.md`

Verification:

- Focused queue/runtime tests passed.
- Factory control runtime preflight passed.
- Python syntax compilation passed.
- Full test suite is blocked by missing `pydantic` and `httpx` in the lease environment before changed tests run.

Risks:

- The Redis queue operations remain non-transactional, matching the existing sidecar pattern. Duplicate guards reduce repeat insertion but do not provide strict multi-worker atomicity.
- Reconciliation currently runs on selected status/read paths and lease polling, not from a dedicated background scheduler.

Rollback:

- Revert this branch commit or remove the added reconciliation/status changes from `ops/factory_control.py` and the focused tests.

