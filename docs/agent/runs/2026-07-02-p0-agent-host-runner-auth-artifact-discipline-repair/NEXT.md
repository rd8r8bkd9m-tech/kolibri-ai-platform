# Next

Next exact task:

`P0_AGENT_HOST_RUNNER_AUTH_ARTIFACT_DISCIPLINE_PR_RELEASE_GATE_2026_07_02`

Objective:

Open and review the repair branch for Agent Host runner auth/artifact
discipline. If CI and review pass, merge through the normal PR path, then run a
remote canary that verifies:

1. Empty worktree checkout failures produce `worktree_checkout_failed`.
2. Missing required artifacts produce a blocked result with repair/rerun
   metadata.
3. Factory Control persists repair metadata from `/fail` for dispatcher use.

Do not retry direct `main` push or live runtime mutation from this task.
