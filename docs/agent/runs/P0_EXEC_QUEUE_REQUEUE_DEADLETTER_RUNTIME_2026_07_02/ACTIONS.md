# ACTIONS

Implemented code changes:

- Added `dead_letter_ids()`, `enqueue_once()`, and `dead_letter_once()` in `ops/factory_control.py`.
- Changed expired lease reconciliation to return a summary: inspected, requeued, dead_lettered.
- Added bounded `runtime_events` records for lease expiry decisions.
- Removed stale queue entries before requeue/dead-letter decisions.
- Requeued expired tasks only once when retry budget remains.
- Moved expired tasks to `dead_letter` only once when retry budget is exhausted.
- Triggered runtime reconciliation from:
  - `GET /v1/tasks`
  - `GET /v1/tasks/{task_id}`
  - `GET /v1/agents/status/{task_id}`
  - `GET /v1/agents/artifacts/{task_id}`
  - `GET /v1/superfactory/status`
  - `GET /v1/superfactory/tasks/{task_id}/artifacts`
- Exposed `dead_letter` and `runtime_reconciliation` in task and superfactory status payloads.

Implemented tests:

- Added an in-memory Redis fake in `tests/test_factory_runtime_queue_contracts.py`.
- Added tests for:
  - expired running lease requeues exactly once;
  - expired leased task dead-letters when retries are exhausted;
  - superfactory status reconciles expired review leases and exposes dead-letter state.

