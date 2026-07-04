# Next

Immediate next action:

Keep the PR #125 lease repair at this bounded canary stage. Do not start a full worker wave from this task.

Before broader rollout:

1. Owner or authenticated GitHub automation should confirm current PR #125 GitHub check-run status in GitHub, because this node cannot access private check-runs through unauthenticated REST and `gh` is not logged in.
2. Run a separate owner-approved rollout canary on `primary-candidate` or `highload` if the fleet should validate outside `main`.
3. If rollback is required later, use the rollback record in `ROLLBACK_RECORD.md` and account for later route/admin runtime changes before restoring the older `before` binary.
4. Keep qjns/uiap excluded from runtime deploy/canary tasks unless their runner capability and owner credential gates are explicitly repaired.

Suggested exact follow-up task:

`P0_PR125_AUTHENTICATED_GITHUB_CHECK_AND_PRIMARY_CANDIDATE_CANARY_2026_07_04`

Scope for that follow-up:

- Authenticate GitHub check-run read.
- Verify PR #125 check conclusion.
- Run the same 20/50/100/250 synthetic lease canary on `primary-candidate` or another healthy routed node.
- Do not requeue a full worker wave.

