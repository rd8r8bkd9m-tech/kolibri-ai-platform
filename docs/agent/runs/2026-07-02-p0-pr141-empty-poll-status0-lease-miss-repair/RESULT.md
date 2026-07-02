# RESULT

Status: implementation complete locally on primary-candidate branch `codex/pr141-empty-poll-status0-lease-miss`.

Repair:

- Added an accept-loop warmed-empty fast path for valid ordinary `/v1/tasks/lease` POSTs. It returns the existing compact `200/no_task` payload before the request waits in the capped worker executor.
- The fast path waits until the full small HTTP request is available and drains it before responding, avoiding client-side reset/status `0` caused by closing while the POST body is still being sent.
- Strengthened `lease_persisted_queued_task` so if the bounded random queued-index sample does not find a compatible task, it performs a full queued-index recovery sweep before returning `no_task`.

Changed files:

- `ops/factory_control.py`
- `tests/test_factory_capacity_controls.py`
- `docs/agent/runs/2026-07-02-p0-pr141-empty-poll-status0-and-lease-miss-repair/*`

Boundary:

- No runtime deployment was performed.
- No service restart was performed.
- No live canary was run from this implementation task.
