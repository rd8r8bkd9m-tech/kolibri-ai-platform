# Plan

Task id:
`P0_AUTOPILOT_EXTRA_35_HOME_WALLBOARD_RUSSIAN_STATUS_2026_07_02`

Owner-facing agent:
`Ольга — Documentation Curator`

Node:
`kolibri`

Execution context:
server-side mesh worker worktree under
`/var/lib/kolibri-agent/logical-workers/mesh-agent-35/.../repo`.

Scope:

- Improve the remote status reporting plan for the Home wallboard in Russian.
- Keep this run documentation/artifacts-only.
- Do not edit product code, UI code, runtime services, secrets, or main branch.
- Define the next exact PR-scoped implementation task before any product code changes.

Wallboard reporting contract:

| Section | Russian title | Required content |
| --- | --- | --- |
| Status | `Статус фабрики` | overall state, freshness time, source confidence |
| Visible tasks | `Видимые задачи` | task id, Russian owner label, state, node, agent, artifact path, next action |
| Active agents | `Активные агенты` | Russian display name, role, node, current task, heartbeat/freshness |
| Blockers | `Блокеры` | blocker, severity, owner action required, exact repair task |
| Next actions | `Следующие действия` | one exact next task, owner decision if needed, safe execution node |
| Safety | `Ограничения безопасности` | no secrets, no Mac-local product edits, no force push, no push to main |

Source priority:

1. Exact Control Plane task lookup for specific P0 task IDs.
2. Canonical run artifacts under `docs/agent/runs/...`.
3. Dispatcher source-of-truth summaries in `docs/agent/dispatcher/FACTORY_STATUS.md`,
   `REMOTE_RESULTS.md`, and `REMOTE_AGENTS.md`.
4. GitHub PR/CI metadata only from authenticated server-side checks or existing
   recorded artifacts.

Freshness rules:

- Show task state as fresh only when the state was checked by exact task ID.
- If only committed artifacts are available, mark the card as `по артефактам`.
- If a task is queued/running without fresh heartbeat evidence, show
  `требует перепроверки`, not `готово`.

