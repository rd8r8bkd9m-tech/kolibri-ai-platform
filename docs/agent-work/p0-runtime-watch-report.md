# P0 runtime watch report

Date: 2026-06-29
Role: runtime P0 observer
Target task: `KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629`

## Scope

This report is a local, non-mutating watch note. During this pass I only read
repository documents and local files. I did not touch live servers, did not
submit/cancel/requeue/drain tasks, did not restart services, and did not run
FormulaLM or any LLM workload on this Mac.

Relevant local sources:

- `ops/envelopes/KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629.json`
- `docs/agent-work/factory-p0-live-repair-status.md`
- `docs/API-RU.md`
- `docs/agent-work/docs-steward.md`
- `docs/agent-work/control-plane-queue-unblock-report.md`

## Last documented status

The latest local status document says the rerun task was accepted by Control
Plane, leased by `main:agent-host-main`, and observed as:

```text
GET /v1/tasks/KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629
state=running
lease_owner=main:agent-host-main
error=null
```

Treat this as the last documented snapshot, not as a fresh live observation
from this watcher pass.

The envelope defines the intended route and acceptance:

- `kind=generic_implementation`
- `required_capability=implementation`
- `target_node=main`
- `runner=codex`
- `create_review_on_complete=true`
- `review_node=new`

The task goal is P0 app recovery after agent-host runtime rollout. It must not
cancel, requeue, drain, restart, or mutate other Control Plane tasks. If Codex
runner, deployment credentials, or production access are unavailable on the
node, it must produce a blocker artifact instead of claiming completion.

## What `running` means

`running` means an Agent Host has an active task lease and is refreshing task
heartbeat metadata through `POST /v1/tasks/<task_id>/heartbeat`. For this P0
rerun, meaningful `running` evidence must show:

- `state=running` for `KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629`.
- `lease_owner=main:agent-host-main` or another explicitly accepted fresh
  implementation executor. Any unexpected owner is a routing finding.
- `lease_until` is in the future relative to the snapshot time.
- `heartbeat_at` is fresh under the configured lease/stale thresholds.
- Runtime metadata, if present, matches the envelope branch
  `agent/KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629/app-unblock`.
- `error=null`, `error_type=null`, and no terminal `result` yet.

Do not count the task as healthy running if heartbeat is stale, lease is
expired, or only a broad queue count changed. Previous reports show that broad
`summary`, `compact`, `limit`, and `state` views can be misleading; targeted
task status is the authoritative watch primitive.

## What `completed` means

`completed` is terminal success. For this task it is not enough to see the
state alone; evidence must prove that acceptance was actually closed.

Required completion evidence:

- Targeted task status shows `state=completed`.
- `result` and/or `result_reference` exists.
- Result includes exact commands and checks run by the executor, especially:
  `npm --prefix frontend run lint --if-present`,
  `npm --prefix frontend run build`, and
  `python3 -m compileall -q backend ops`, unless the result explains why a
  command was not applicable.
- Result identifies changed files, or states that no repository change was
  needed.
- Result explains the owner app diagnosis category: frontend, Telegram Mini
  App, domain/dev-server, Control Plane status, deployment, or blocker.
- Evidence confirms `/app` remains chat-first and the Control entrypoint remains
  owner-safe.
- If a commit/PR was produced, result contains the branch and PR URL; because
  `create_review_on_complete=true`, absence of PR data may place the task in
  `waiting_review` rather than final `completed`.
- Owner-facing summary is sanitized: no raw logs, secrets, local-only paths, or
  internal node details unless explicitly requested by the operator.

If the task has `waiting_review`, it should be treated as implementation done
but not fully closed. The next evidence to gather is review task/PR routing to
`new`, review result, and the eventual transition to `completed`.

## What `failed` means

`failed` is terminal failure after the task runner reported an error or retry
budget was exhausted. For this P0 rerun, `failed` should not be treated as
"nothing happened"; it must produce a blocker trail.

Required failure evidence:

- Targeted task status shows `state=failed`.
- `error_type` and `error` are present and specific enough to classify the
  failure.
- `result` and/or `result_reference` points to a blocker artifact, or the
  absence of that artifact is called out as a reporting defect.
- The blocker says whether the missing dependency is Codex runner support,
  deployment credentials, production access, frontend/build failure, Telegram
  Mini App/domain issue, Control Plane/API issue, or another concrete cause.
- Attempt metadata shows whether this was the first attempt or retry-exhausted
  failure.
- Evidence confirms the task did not mutate unrelated queued or stale-running
  Control Plane tasks.

If the state is `dead_letter`, `cancelled`, or `retry_scheduled`, do not map it
to plain failed without the exact state. `retry_scheduled` is transient; wait
for the next targeted status before writing a terminal conclusion.

## Evidence collection checklist

For a future read-only watcher pass, collect evidence in this order:

1. Targeted task status for
   `KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629`, full shape if available.
2. Current `/health` timestamp and Redis/backend status.
3. Node card for `main`: freshness, `draining`, capabilities, active task, and
   heartbeat age.
4. If task is `running`: lease owner, lease expiry, heartbeat freshness, branch,
   worktree metadata, and absence of errors.
5. If task is `completed`: result/result_reference, command evidence, changed
   files, PR/review routing, app evidence, and sanitized owner summary.
6. If task is `failed`: error_type/error, blocker artifact, attempt history, and
   whether retry budget remains.
7. Agent messages around the task: `task_started`, progress notes,
   `task_completed`, `task_failed`, blocker, or review request.
8. Do not rely on queue length alone. Record queue count only as supporting
   context, not as proof of this task's progress.

## Safe local checks performed

Commands run in this observer pass:

```bash
pwd
git status --short
sed -n '1,220p' /Users/kolibri/.codex/skills/kolibri-factory-admin/SKILL.md
sed -n '1,260p' /Users/kolibri/.codex/skills/kolibri-factory-admin/references/runbook.md
rg -n "KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629|APP-QUEUE|QUEUE-UNBLOCK|running|completed|failed" docs ops tests -S
sed -n '1,180p' docs/agent-work/factory-p0-live-repair-status.md
sed -n '1,140p' ops/envelopes/KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629.json
sed -n '340,650p' docs/API-RU.md
sed -n '520,620p' docs/agent-work/docs-steward.md
```

No live Control Plane command was executed in this pass.

