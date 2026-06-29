# GitHub/main execution operator report

Дата: 2026-06-29
Роль: Оператор GitHub/main и серверных поручений
Репозиторий: `rd8r8bkd9m-tech/kolibri-ai-platform`
Scope: read-only proof, GitHub/main execution plan, Control Plane task
envelopes. Коммит, push, PR update, merge и submit задач не выполнялись.

## 1. Read-only proof выполнен

Локальные команды, выполненные из workspace:

```bash
git status --short --branch
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
git ls-remote --heads origin main
git config --get remote.origin.url
git rev-parse --abbrev-ref --symbolic-full-name @{upstream}
git rev-list --left-right --count origin/main...HEAD
git rev-list --left-right --count @{upstream}...HEAD
git ls-remote --heads origin codex/factory-autonomy-pwa-billing
git merge-base origin/main HEAD
git merge-tree --write-tree origin/main origin/codex/factory-autonomy-pwa-billing
```

Дополнительно выполнены read-only проверки через GitHub connector:

- PR #46 metadata;
- compare `main...codex/factory-autonomy-pwa-billing`;
- workflow runs for PR head SHA;
- workflow run jobs for run `28360693208`;
- classic combined commit statuses for PR head SHA.

`gh` в этом workspace отсутствует: `command -v gh` вернул exit code `1` и
пустой вывод. Поэтому PR/CI доказательства ниже получены через GitHub connector,
а не через GitHub CLI.

Control Plane read-only proof также выполнен без queue mutations:

- `GET /health`;
- `GET /v1/nodes` с безопасной сводкой по target nodes;
- `GET /v1/tasks?summary=1&compact=1&limit=20`;
- targeted `GET /v1/tasks/<task_id>` для известных утренних task ids.

## 2. GitHub/main state

Текущий origin:

```text
https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform.git
```

Текущая PR-ветка:

```text
codex/factory-autonomy-pwa-billing
```

Refs:

| Ref | SHA |
| --- | --- |
| `origin/main` | `6d0317c52a9694448ee2c352dc196ce7a27b9487` |
| `HEAD` | `8222c179cc7df34caf60565c797ba8c55829dd78` |
| `origin/codex/factory-autonomy-pwa-billing` | `8222c179cc7df34caf60565c797ba8c55829dd78` |
| merge-base `origin/main...HEAD` | `6d0317c52a9694448ee2c352dc196ce7a27b9487` |

Ahead/behind:

```text
origin/main...HEAD: 0 behind / 25 ahead
@{upstream}...HEAD: 0 behind / 0 ahead
```

GitHub compare confirmed the same state:

```text
status=ahead
ahead_by=25
behind_by=0
total_commits=25
base_commit=6d0317c52a9694448ee2c352dc196ce7a27b9487
merge_base_commit=6d0317c52a9694448ee2c352dc196ce7a27b9487
```

Local mergeability proof:

```text
git merge-tree --write-tree origin/main origin/codex/factory-autonomy-pwa-billing
result tree: f2aeccf8893bfb861803babe4a5962172b93f2ac
exit code: 0
```

`git status --short --branch` showed the workspace already had unrelated
modified and untracked files before this report. I did not revert, stage, or
edit those files. This task adds only this report file.

## 3. PR #46 state and CI evidence

PR:

```text
https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/46
```

GitHub connector snapshot:

| Field | Value |
| --- | --- |
| title | `[codex] Factory autonomy, PWA billing, remote FormulaLM` |
| state | `open` |
| draft | `true` |
| merged | `false` |
| base | `main` |
| base SHA | `6d0317c52a9694448ee2c352dc196ce7a27b9487` |
| head | `codex/factory-autonomy-pwa-billing` |
| head SHA | `8222c179cc7df34caf60565c797ba8c55829dd78` |
| mergeable | `true` |
| commits | `25` |
| changed files | `232` |
| additions / deletions | `43223` / `700` |
| tentative merge commit | `32e7e31803a75f282a2292b91fcc0ad5e9ac1c51` |

CI evidence for head SHA `8222c179cc7df34caf60565c797ba8c55829dd78`:

| Evidence | Result |
| --- | --- |
| Workflow | `Kolibri CI` |
| Run id | `28360693208` |
| Run number | `192` |
| Workflow status | `completed` |
| Workflow conclusion | `success` |
| Job | `ci` |
| Job id | `84014347268` |
| Job status | `completed` |
| Job conclusion | `success` |
| Classic combined statuses | empty list |

Successful job steps included Python syntax compile, pytest tests, JavaScript
and TypeScript checks, JSON/YAML validation, repository secret check, production
secret path guard, and local component smoke.

CI limitation: the available connector proof covered GitHub Actions workflow
runs and classic statuses. Because local `gh` is absent, I did not run
`gh pr checks` or fetch full branch-protection UI state from this workspace.
Before merge, verify required checks on the exact head SHA in GitHub.

## 4. Why `main` does not match the live factory

`origin/main` is not current relative to the factory work because it is exactly
the merge-base of PR #46 and is missing 25 commits now present on the PR branch.
Those commits contain the factory/runtime changes currently needed to describe
and operate the live system:

- Control Plane task-list fast path and state indexes;
- canonical cluster node summaries;
- runtime compatibility for implementation task kinds;
- Agent Host runner result capture and empty-response fallback;
- deliverable evidence gate and deliverable failure visibility;
- lease watchdog, stuck-task sweep, watchdog Telegram/reporting path;
- PWA/billing/autonomy docs and envelopes;
- remote-only FormulaLM harness with Mac execution blocked by design.

Fresh read-only Control Plane proof at `2026-06-29T11:52:29Z`:

```text
health.status=ok
health.redis=PONG
health.queue_backend=redis
node_count=5
task summary returned_tasks=2
queue_total=2
state_counts_returned={"queued": 2}
```

Target node state from the fresh proof:

| Node | Current proof |
| --- | --- |
| `main` | online, non-draining, active_task=null, capabilities include `implementation`, `review`, `read_only_probe` |
| `new` | online, non-draining, active_task=null, capabilities include `review`, `read_only_probe`, `generic_review` |
| `primary-candidate` | online, non-draining, active_task=null, capabilities include `implementation`, `review`, `generic_implementation`, `generic_review` |
| `qjns` | online, non-draining, active_task=null, capabilities include `implementation`, `review`, `qa`, `agent-host` |
| `9fts` | absent from current `/v1/nodes` proof |

Targeted status reads for old morning tasks returned `404 Not Found`:

```text
TG-20260629003017-4711-up-telegram
TGCHAT-20260629003136-4713-kolibri
KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629
KOL-P0-APP-VERIFY-REVIEW-20260629
KOL-SERVER-KFRM-PROBE-20260629
```

This differs from earlier local reports on 2026-06-29 that documented 35 node
cards, dozens of queued tasks, stale `9fts`, stale or risky
`primary-candidate`, and `qjns` as draining or runtime-incomplete. I treat the
fresh Control Plane proof as authoritative for current routing, and the older
reports as historical incident context. The mismatch itself is an operations
risk: GitHub `main`, PR #46, and live Control Plane state are not one shared
truth yet.

## 5. Merge gates required

Do not sync `main` until all gates are explicit:

1. PR #46 is still `draft=true`. Owner must approve moving it to ready or
   explicitly approve merging a draft.
2. Expected head SHA must be pinned before any PR action:
   `8222c179cc7df34caf60565c797ba8c55829dd78`.
3. CI/required checks must be green on that exact SHA. Current evidence shows
   `Kolibri CI` success, but local `gh` is unavailable for branch-protection
   rollup verification.
4. Use a clean temporary worktree for local pre-merge checks because this
   workspace has unrelated dirty files.
5. No direct `main` ref update. Prefer GitHub PR merge with expected head SHA.
6. No FormulaLM or model benchmark on this Mac. FormulaLM stays remote-only and
   must run through Control Plane after server gates.
7. After merge, verify `origin/main` contains PR head in history. If the owner
   requires literal `origin/main == 8222c179...`, that is a separate
   fast-forward ref decision and not implied by normal PR merge.

## 6. Execution order: no simulation as completion

The required operator order is:

```bash
git status --short --branch
git add docs/agent-work/github-main-execution-operator-20260629.md
git commit -m "docs: add github main execution operator report"
git push origin codex/factory-autonomy-pwa-billing
```

Then update PR #46 only after the push is real:

```text
PR update:
- add link/path to this report;
- include current head SHA;
- include CI evidence;
- state that server envelopes are prepared but not submitted.
```

Then wait for CI on the new head:

```text
Required:
- GitHub Actions checks completed/success;
- branch protection requirements satisfied;
- owner ready/merge approval recorded.
```

Then main sync:

```bash
git fetch origin '+refs/heads/main:refs/remotes/origin/main'
git merge-base --is-ancestor 8222c179cc7df34caf60565c797ba8c55829dd78 origin/main
git log --oneline -n 5 origin/main
```

Do not present `merge-tree` output, a local dry-run, or an unpushed commit as
main synchronization. Those are only proof steps.

## 7. Control Plane preflight commands

Set the Control Plane URL without secrets:

```bash
export KOLIBRI_FACTORY_CONTROL_URL=http://10.99.0.2:9101
```

Read-only preflight before any submit:

```bash
curl -fsS --max-time 5 "$KOLIBRI_FACTORY_CONTROL_URL/health"
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" nodes
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" status --limit 20
```

Submission command shape for every envelope below:

```bash
python3 -m json.tool /tmp/kolibri-ghmain-envelopes/<file>.json >/dev/null
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" submit --file /tmp/kolibri-ghmain-envelopes/<file>.json
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" status <TASK_ID> --full
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" collect <TASK_ID>
```

The JSON blocks below are not submitted by this report. Submit only after the
gates in each envelope are satisfied.

## 8. Server task envelope: `main`

Назначение: Исполнитель `main` - проверка после merge и минимальные проверки репозитория.

Use after PR #46 is merged or after owner explicitly requests a pre-merge smoke
against the PR branch.

Filename:

```text
/tmp/kolibri-ghmain-envelopes/KOL-GHMAIN-MAIN-POSTMERGE-SMOKE-20260629.json
```

Envelope:

```json
{
  "task_id": "KOL-GHMAIN-MAIN-POSTMERGE-SMOKE-20260629",
  "idempotency_key": "github-main:main-postmerge-smoke:2026-06-29",
  "kind": "generic_implementation",
  "required_capability": "implementation",
  "target_node": "main",
  "permission_pack": "implementation",
  "runner": "codex",
  "branch": "agent/KOL-GHMAIN-MAIN-POSTMERGE-SMOKE-20260629/main-smoke",
  "base_ref": "origin/main",
  "role_slot": "Исполнитель main",
  "role_goal": "Проверить, что main после синхронизации реально содержит PR #46 и проходит минимальные безопасные проверки",
  "goal": "Снять post-merge GitHub/main proof после реального merge PR #46. Проверить origin/main, наличие PR head в истории, health Control Plane, минимальные Python/frontend smoke checks. Если найден малый docs/report дефект, исправить его отдельным branch result; если нужен deploy или секреты, вернуть blocker artifact. Не выполнять deploy, queue surgery, force push или FormulaLM/model workloads.",
  "acceptance": [
    "origin/main содержит 8222c179cc7df34caf60565c797ba8c55829dd78 в истории или явно сообщает, что merge еще не выполнен",
    "Записаны exact commands and results",
    "Проверки не запускают FormulaLM, Qwen, Ollama, vLLM или другие model workloads",
    "Если были изменения, создана review-ready branch; если изменений нет, result содержит checks evidence",
    "Owner-facing summary не содержит секретов, raw logs или local-only paths"
  ],
  "verification_commands": [
    "git status --short --branch",
    "git fetch origin '+refs/heads/main:refs/remotes/origin/main'",
    "git merge-base --is-ancestor 8222c179cc7df34caf60565c797ba8c55829dd78 origin/main",
    "python3 -m compileall -q backend ops tests",
    "npm --prefix frontend run build"
  ],
  "max_retries": 1,
  "create_review_on_complete": true,
  "review_node": "new",
  "source": {
    "kind": "github_main_execution_operator",
    "created_at": "2026-06-29",
    "report": "docs/agent-work/github-main-execution-operator-20260629.md",
    "not_submitted_by_report": true
  }
}
```

## 9. Server task envelope: `new`

Назначение: Проверяющий `new` - независимая PR/main проверка.

Use after this report is pushed to PR #46 or after the owner requests
independent review.

Filename:

```text
/tmp/kolibri-ghmain-envelopes/KOL-GHMAIN-NEW-PR46-REVIEW-20260629.json
```

Envelope:

```json
{
  "task_id": "KOL-GHMAIN-NEW-PR46-REVIEW-20260629",
  "idempotency_key": "github-main:new-pr46-review:2026-06-29",
  "kind": "review_pr",
  "required_capability": "review",
  "target_node": "new",
  "pull_request_url": "https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/46",
  "base_ref": "origin/main",
  "role_slot": "Проверяющий new",
  "role_goal": "Независимо проверить PR #46, CI evidence, report link и merge gates",
  "goal": "Проверить PR #46 как reviewer: head SHA, draft state, CI, changed files, report link, отсутствие обещания merge без owner gate. Не менять PR state, не делать merge, не пушить в main.",
  "acceptance": [
    "Отчет reviewer содержит PR URL, head SHA, base SHA и CI verdict",
    "Отдельно указано, что PR draft или owner gate блокирует merge, если gate не снят",
    "Не выполнялись merge, rebase, force push, PR ready, PR close или queue mutations",
    "Telegram/owner summary sanitized"
  ],
  "max_retries": 1,
  "source": {
    "kind": "github_main_execution_operator",
    "created_at": "2026-06-29",
    "report": "docs/agent-work/github-main-execution-operator-20260629.md",
    "not_submitted_by_report": true
  }
}
```

## 10. Server task envelope: `primary-candidate`

Назначение: Кандидат `primary-candidate` - read-only gate перед задачами реализации.

Fresh proof now shows `primary-candidate` online and non-draining, but older
reports describe stale/dead-letter risk. Therefore first task must be a
read-only lease/artifact gate, not implementation workload.

Filename:

```text
/tmp/kolibri-ghmain-envelopes/KOL-GHMAIN-PRIMARY-PARITY-PROBE-20260629.json
```

Envelope:

```json
{
  "task_id": "KOL-GHMAIN-PRIMARY-PARITY-PROBE-20260629",
  "idempotency_key": "github-main:primary-candidate-parity-probe:2026-06-29",
  "kind": "read_only_probe",
  "required_capability": "read_only_probe",
  "target_node": "primary-candidate",
  "role_slot": "Кандидат primary",
  "role_goal": "Доказать lease/artifact readiness primary-candidate перед любым implementation workload",
  "goal": "Read-only probe for primary-candidate after fresh Control Plane snapshot. The task must prove that the node can lease and complete through node-local artifacts. It must not run implementation, model workloads, queue surgery, service restarts, deploys, or GitHub writes.",
  "acceptance": [
    "Task is leased by primary-candidate",
    "Task completes through node-local artifact result",
    "Result confirms node_id=primary-candidate",
    "No implementation workload, no FormulaLM/model workload, no queue mutation"
  ],
  "max_retries": 1,
  "source": {
    "kind": "github_main_execution_operator",
    "created_at": "2026-06-29",
    "report": "docs/agent-work/github-main-execution-operator-20260629.md",
    "not_submitted_by_report": true,
    "fresh_proof": "2026-06-29T11:52:29Z primary-candidate online non-draining active_task=null"
  }
}
```

## 11. Server task envelope: `qjns`

Назначение: Проверяющий `qjns` - read-only lease gate перед QA-проверками.

Fresh proof now shows `qjns` online and non-draining. Older reports describe
runtime/toolchain gaps. First task remains read-only.

Filename:

```text
/tmp/kolibri-ghmain-envelopes/KOL-GHMAIN-QJNS-RUNTIME-PROBE-20260629.json
```

Envelope:

```json
{
  "task_id": "KOL-GHMAIN-QJNS-RUNTIME-PROBE-20260629",
  "idempotency_key": "github-main:qjns-runtime-probe:2026-06-29",
  "kind": "read_only_probe",
  "required_capability": "read_only_probe",
  "target_node": "qjns",
  "role_slot": "Проверяющий qjns",
  "role_goal": "Доказать безопасный lease/artifact path qjns перед проверкой или QA задачами",
  "goal": "Read-only lease probe for qjns. Do not assign implementation, Mimo, Codex, frontend build, FormulaLM, or QA workload until the probe completes and a separate runtime/toolchain readiness task is approved.",
  "acceptance": [
    "Task is leased by qjns",
    "Task completes through node-local artifact result",
    "Result confirms node_id=qjns",
    "No model workload, no service restart, no queue mutation"
  ],
  "max_retries": 1,
  "source": {
    "kind": "github_main_execution_operator",
    "created_at": "2026-06-29",
    "report": "docs/agent-work/github-main-execution-operator-20260629.md",
    "not_submitted_by_report": true,
    "fresh_proof": "2026-06-29T11:52:29Z qjns online non-draining active_task=null"
  }
}
```

## 12. Server task envelope: `9fts`

Назначение: Сверка `9fts` - gate для отсутствующего или ранее stale owner-task исполнителя.

Fresh proof did not include `9fts` in `/v1/nodes`. Do not submit this envelope
until a fresh `/v1/nodes` read shows `9fts` online, non-draining, and capable of
`read_only_probe`. If submitted while absent, it will likely become a new queued
blocker instead of resolving the old incident.

Filename:

```text
/tmp/kolibri-ghmain-envelopes/KOL-GHMAIN-9FTS-RETURN-PROBE-20260629.json
```

Envelope:

```json
{
  "task_id": "KOL-GHMAIN-9FTS-RETURN-PROBE-20260629",
  "idempotency_key": "github-main:9fts-return-probe:2026-06-29",
  "kind": "read_only_probe",
  "required_capability": "read_only_probe",
  "target_node": "9fts",
  "role_slot": "Сверка 9fts",
  "role_goal": "Доказать, что 9fts вернулся как реальный executor, прежде чем связывать его со старыми owner tasks",
  "goal": "Read-only return probe for 9fts. Run only after 9fts appears fresh in /v1/nodes. Do not cancel or mutate old Telegram tasks, do not run app recovery, and do not claim owner-task recovery without a completed 9fts lease result.",
  "acceptance": [
    "Preflight /v1/nodes shows 9fts online and non-draining",
    "Task is leased by 9fts",
    "Task completes through node-local artifact result",
    "No duplicate owner app task, no queue mutation, no manual retry/cancel"
  ],
  "max_retries": 1,
  "source": {
    "kind": "github_main_execution_operator",
    "created_at": "2026-06-29",
    "report": "docs/agent-work/github-main-execution-operator-20260629.md",
    "not_submitted_by_report": true,
    "current_blocker": "2026-06-29T11:52:29Z 9fts absent from /v1/nodes read-only proof"
  }
}
```

## 13. Secret check policy for this report

This report must not contain credentials, API tokens, cookies, private keys,
auth cache contents, `.env` values, or raw production logs.

Local verification command to run after editing:

```bash
rg -n "(ghp_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]+|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY|Bearer [A-Za-z0-9._-]{20,}|password\\s*=|token\\s*=|api[_-]?key\\s*=)" docs/agent-work/github-main-execution-operator-20260629.md
```

Expected result: no matches.

## 14. Operator conclusion

`origin/main` is Git-clean relative to the PR branch only in the sense that it
is the merge-base. It is not operationally current. PR #46 is ahead by 25
commits, mergeable by GitHub, and currently has green GitHub Actions evidence on
head `8222c179cc7df34caf60565c797ba8c55829dd78`, but it is still draft and must
not be merged without owner gate and required-check confirmation.

The live Control Plane is reachable and currently much smaller/cleaner than the
earlier incident reports: 5 node cards and 2 queued tasks in the fresh proof.
That improves routing options for `primary-candidate` and `qjns`, but it also
means old task ids and old queue counts are not current truth. The safe path is
to commit this report to the PR branch, push, update PR #46, wait for CI, then
sync `main` through the PR process. Server work should start with read-only
lease probes and only then proceed to implementation/review workloads.
