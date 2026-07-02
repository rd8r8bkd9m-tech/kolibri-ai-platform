# Actions

Task id: `P0_QUEUE_GUARDIAN_REQUEUE_AND_DEADLETTER_POLICY_2026_07_02`

Status: `implemented`

Lease owner: `mesh-agent-04:autonomous_engineer`

Actions:

- Added queue guardian state constants and read-only classification helpers in `ops/factory_control.py`.
- Added artifact extraction for task result paths used by the guardian record.
- Added `queue_guardian_policy` to emit `task_id`, `status`, `lease_owner`, `artifacts`, `blockers`, `next_action`, and policy metadata per task.
- Added `queue_guardian_snapshot` to classify queued, failed, running, and dead_letter backlog and produce a sorted first repair queue.
- Added read-only API aliases: `GET /v1/tasks/backlog/guardian` and `GET /v1/queue/guardian`.
- Added tests for core backlog classification and owner-gated broad retry/supersede policy.

No broad cancel, requeue, retry, or supersede mutation was added.
