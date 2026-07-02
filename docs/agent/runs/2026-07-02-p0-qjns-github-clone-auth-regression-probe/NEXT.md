# Next

Immediate next action:

Route one low-risk real read-only review canary to qjns using an existing small PR branch, with broad pytest and GitHub review submission disabled or separately gated. The current Agent Host `review_pr` runner proves clone first, but its normal success path can continue into checkout, compile, broad tests, and optional `gh pr review`; use a narrower clone-only task kind for future auth regression checks.

Owner-safe repair recommendation:

No qjns GitHub credential repair is required for noninteractive clone based on this canary. Keep the current node-scoped credential in place and avoid rotating it unless owner-approved key rotation is scheduled.

Follow-up engineering task:

Add an explicit Agent Host `git_clone_probe` task kind that:

- targets one node,
- runs `git clone --filter=blob:none --no-checkout` or `git ls-remote`,
- sets `GIT_TERMINAL_PROMPT=0`,
- never checks out a branch,
- never runs tests,
- never calls `gh pr review`,
- writes a structured `result.json` for both success and failure,
- exposes failed-task artifacts through `/v1/agents/artifacts/{task_id}`.

Routing guidance:

- qjns may re-enter lightweight review/QA routing for clone-dependent tasks.
- Keep qjns out of heavy build/test workloads until disk reserve is reviewed; free space was about `4.86 GB` during this probe.
- Do not use direct SSH as the normal repair path; Control Plane and Agent Host are the working server-side path.
