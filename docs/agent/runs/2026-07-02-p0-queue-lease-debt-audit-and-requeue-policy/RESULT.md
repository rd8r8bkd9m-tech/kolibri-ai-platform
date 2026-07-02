# Result

State: `implemented_with_live_probe_blocker`

Node:
- Host: `kolibri`
- Role: server Agent Host worktree
- Branch: `agent/P0_QUEUE_LEASE_DEBT_AUDIT_AND_REQUEUE_POLICY_2026_07_02/generic`

Artifacts:
- `PLAN.md`
- `ACTIONS.md`
- `TESTS.md`
- `BACKLOG_REQUEUE_POLICY.md`
- `RESULT.md`
- `NEXT.md`
- `result.json`

Implemented result:
- Factory Control now has a reusable backlog audit classifier for queued, failed, dead-letter, cancelled, and lease-debt tasks.
- Dispatcher exposes `backlog-audit` so operators can request the audit through the remote control plane.
- The policy identifies tasks safe to retry after GitHub clone repair through structured error types and sanitized result/error markers.
- The audit is explicitly non-mutating; requeue/cancel/supersede remain operator-controlled actions.

Blocker:
- Live control plane at the configured dispatcher URL returned HTTP 404 for `/v1/tasks/backlog/audit`, meaning the deployed service has not yet picked up this branch's route. A live current backlog list is therefore blocked until deployment/restart of this change.

Next action:
- Merge/deploy this branch to the server Factory Control service, restart through the approved Agent Host/control-plane deploy path, then run `./ops/kolibri-dispatch backlog-audit` and use `safe_to_retry_after_github_clone_repair` to select GitHub-clone-repair retry candidates.
