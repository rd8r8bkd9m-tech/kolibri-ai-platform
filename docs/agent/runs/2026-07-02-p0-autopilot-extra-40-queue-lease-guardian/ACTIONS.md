# Queue Lease Guardian Actions

- Added queue/dead-letter health inspection in `ops/factory_control.py`.
- Added findings for duplicate queue entries, orphan queue entries, non-queued tasks in queue, queued tasks missing from queue, expired leases, stuck running tasks, dead-letter tasks, and dead-letter list drift.
- Added safe repair envelope generation with stable `queue-lease-guardian:*` idempotency keys.
- Added `GET /v1/tasks/guardian` for read-only inspection.
- Added `POST /v1/tasks/guardian/repair` for explicit idempotent repair task creation.
- Added `kolibri-dispatch guardian` and `kolibri-dispatch guardian --create-repair-tasks`.
- Added focused queue guardian tests.

No secrets were printed. No destructive git commands, force push, push to main, service restart, or live queue mutation was performed.

