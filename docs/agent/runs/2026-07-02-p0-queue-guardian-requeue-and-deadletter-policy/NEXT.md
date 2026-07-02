# Next

Task id: `P0_QUEUE_GUARDIAN_REQUEUE_AND_DEADLETTER_POLICY_2026_07_02`

Status: `ready_for_review`

Lease owner: `mesh-agent-04:autonomous_engineer`

Next action:

- Review and merge through the normal owner-approved PR/release path.
- After deploy, call `GET /v1/tasks/backlog/guardian` or `GET /v1/queue/guardian`.
- Use the returned `first_repair_queue` to dispatch targeted single-task repairs first.
- Require explicit owner approval before broad cancel, requeue, retry, or supersede actions.

Follow-up task:

- Add an owner-authenticated mutation endpoint for single-task guardian actions only after the read-only snapshot has been canaried.
