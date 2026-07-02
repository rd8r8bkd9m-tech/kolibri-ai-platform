# Queue Guardian Policy

Task id: `P0_QUEUE_GUARDIAN_REQUEUE_AND_DEADLETTER_POLICY_2026_07_02`

Status: `implemented`

Lease owner: `mesh-agent-04:autonomous_engineer`

Backlog classes:

| Class | Guardian action | Owner gate |
| --- | --- | --- |
| `queued` and present in queue | lease when compatible Agent Host polls | no |
| `queued` but missing queue index | repair one task queue index after duplicate check | no for single task, yes for batch |
| `leased`/`running`/`review` with active lease | monitor heartbeat | cancel requires owner gate |
| `leased`/`running`/`review` with expired lease and retry budget | allow existing single-task lease reaper retry | broad retry requires owner gate |
| `leased`/`running`/`review` with expired exhausted lease | move single task to `dead_letter` | broad dead-letter move requires owner gate |
| `failed` with retry budget | bounded single-task retry candidate | broad retry requires owner gate |
| `failed` without retry budget | prepare superseding task | yes |
| `dead_letter` | prepare targeted repair or owner-approved retry | yes |

Policy invariant:

Do not cancel, requeue, retry, or supersede broad task sets without explicit owner approval.

First repair queue:

- Dead-letter tasks and exhausted failures first.
- Failed tasks with missing artifacts next.
- Expired running leases next.
- Retry-scheduled and queue-index repair candidates after higher-risk items.

Required per-task record:

- `task_id`
- `status`
- `lease_owner`
- `artifacts`
- `blockers`
- `next_action`
- `policy.action`
- `policy.owner_gate_required`
