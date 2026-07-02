# Next

Exact next task:

`P0_HOME_WALLBOARD_RUSSIAN_STATUS_PR_IMPLEMENTATION_2026_07_02`

Objective:

Open a PR-scoped implementation task for the Home wallboard Russian status
surface. The implementation may edit product/UI code only inside that PR task.
It must consume the reporting contract from
`WALLBOARD_RU_STATUS_PLAN.md` and render owner-facing Russian cards for visible
tasks, active agents, blockers, and next actions.

Required acceptance:

- Product code changes happen only on a PR branch, not on `main`.
- No Mac-local product edits.
- No secrets in logs, artifacts, UI payloads, or tests.
- No force push and no push to `main`.
- Home wallboard has Russian owner-facing labels.
- Each visible task card includes status, node, agent name, blocker if any,
  artifact path, and exact next action.
- Tests or static checks prove long Russian labels fit without overlap.

Suggested owner-facing agent:

`Анна — Frontend/PWA Engineer`

Suggested reviewer:

`Наталья — Anti-Degradation Auditor`

