# Backlog Requeue Policy

This policy is non-mutating. It classifies queue debt before any operator action.

Safe actions:
- `wait`: task is already queued or has an active unexpired lease.
- `requeue_now`: queued state is missing queue membership, or a lease has expired and retry budget remains.
- `requeue_after_github_clone_repair`: failed/dead-letter task is tied to GitHub clone or credential failure. Retry only after Agent Host GitHub clone credentials are repaired and verified.
- `supersede`: task declares a replacement, or failed task has useful artifacts/result references. Prefer a follow-up task instead of a blind retry.
- `blocked`: retry budget exhausted, dead-letter lacks safe retry signal, or the blocker must be repaired first.
- `cancel`: reserved for explicit owner/operator intent. The audit does not cancel automatically.
- `noop`: terminal or already-cancelled task has no safe mutation.

Fields returned per task:
- `task_id`, `state`, `node`, `attempt`, `max_retries`, `retry_budget_remaining`
- `lease_owner`, `lease_until`, `lease_debt_seconds`
- `in_queue`, `in_dead_letter`
- `error_type`, `safe_action`, `reason`
- `safe_to_retry_after_github_clone_repair`
- `superseded_by`, `mutation_contract`

Tasks safe to retry after GitHub clone repair:
- Identified by `safe_to_retry_after_github_clone_repair: true`.
- Triggered by structured error types or redacted evidence containing GitHub clone/auth/credential markers.
- The deployed control plane must be updated before a live fleet-wide list can be produced from `/v1/tasks/backlog/audit`.
