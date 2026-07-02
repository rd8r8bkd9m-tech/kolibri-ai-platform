# Next

Next exact task:

`P0_AGENT_HOST_POST_MERGE_CONTRACT_DEPLOY_CANARY_2026_07_02`

Dispatch only after at least one target node runs the deploy command from `RESULT.md`.

Canary requirements:

- Confirm `kolibri-agent-host.service` is active after restart.
- Submit a no-push/read-only task and verify `push_attempted=false`, `push_blocked=true`, and no `git_push` permission survives.
- Submit a missing-required-artifact task and verify final status is `blocked`, not `completed`.
- Submit a write-scope violation task and verify the violating path is recorded.
- Submit a canonical-run-artifact task with all five exact files and verify `required_artifacts_missing=[]`.
- Record service node id, agent id, lease id, task ids, result artifact paths, and rollback status.

If deploy cannot be performed, use the hard blocker command in `RESULT.md` as the repair instruction for the service owner.
