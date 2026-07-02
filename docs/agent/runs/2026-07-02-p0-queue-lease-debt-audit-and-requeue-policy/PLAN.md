# P0 Queue Lease Debt Audit And Requeue Policy Plan

Task: `P0_QUEUE_LEASE_DEBT_AUDIT_AND_REQUEUE_POLICY_2026_07_02`

Execution node:
- Server Agent Host worktree on host `kolibri`.
- Repository branch: `agent/P0_QUEUE_LEASE_DEBT_AUDIT_AND_REQUEUE_POLICY_2026_07_02/generic`.
- Start commit: `f7ac32c`.

Plan:
1. Add a non-mutating backlog classifier to Factory Control.
2. Classify queued, failed, dead-letter, and lease-debt tasks by safe action.
3. Mark tasks safe to retry after GitHub clone repair only when clone/auth evidence is present.
4. Expose the audit through the Fabric API and dispatcher CLI.
5. Verify with focused runtime tests and record live-control-plane blocker if the deployed service is not updated yet.
