# Primary-development-control rerun, 2026-06-29

Роль: Оператор primary-разработки.  
Task id: `KOL-PRIMARY-DEVELOPMENT-CONTROL-RERUN-20260629`.  
Срез выполнен после runtime recovery primary agent-host, где предыдущая попытка падала на `unsupported task kind: generic_implementation`.

## Итог

Primary-candidate снова исполняет `generic_implementation`: текущая задача висит в live Control Plane как `running` на `primary-candidate:agent-host-primary`, node свежий и имеет capabilities `primary`, `generic_implementation`, `generic_review`, `implementation`, `review`, `read_only_probe`.

Control Plane доступен: `GET /health` через `ops/kolibri-dispatch doctor` вернул `status=ok`, `queue_backend=redis`, `redis=PONG`, время `2026-06-29T12:09:56.822739+00:00`.

Безопасный follow-up подготовлен в `ops/envelopes/KOL-MAIN-CONTROL-PLANE-READONLY-AUDIT-20260629.json` и отправлен через `ops/kolibri-dispatch submit`. Это только `read_only_probe` для `main`, без изменений репозитория, очереди, GitHub, деплоя, FormulaLM или model benchmark. Task завершился `completed` на `main:agent-host-main`, result_reference: `/var/lib/kolibri-agent/artifacts/KOL-MAIN-CONTROL-PLANE-READONLY-AUDIT-20260629/KOL-MAIN-CONTROL-PLANE-READONLY-AUDIT-20260629-attempt-1/result.json`.

## Git и PR #46

- Текущая локальная ветка: `agent/KOL-PRIMARY-DEVELOPMENT-CONTROL-RERUN-20260629/primary-control`.
- Upstream текущей ветки: `origin/codex/factory-autonomy-pwa-billing`.
- `HEAD`: `fcfd0f658ef0271197c8b5d5f47d5210b2df04c9`.
- `origin/codex/factory-autonomy-pwa-billing`: `fcfd0f658ef0271197c8b5d5f47d5210b2df04c9`.
- `origin/main`: `6d0317c52a9694448ee2c352dc196ce7a27b9487`.
- Merge-base `origin/main..origin/codex/factory-autonomy-pwa-billing`: `6d0317c52a9694448ee2c352dc196ce7a27b9487`.
- Ahead/behind для `origin/main...origin/codex/factory-autonomy-pwa-billing`: `0 27`, то есть PR-ветка на 27 commits впереди `main` и не отстает от `origin/main`.
- `refs/pull/46/head`: `fcfd0f658ef0271197c8b5d5f47d5210b2df04c9`.
- `refs/pull/46/merge`: `e6dd149296e4c5e3f0db8fa8087fa33cc2655729`.

GitHub blocker: в этом runtime нет `gh` (`/bin/bash: gh: command not found`), `git credential fill` не дал токен, а неаутентифицированный GitHub REST для private repo вернул `404 Not Found`. Поэтому свежие поля PR #46 (`state`, `draft`, `mergeable_state`) и свежий CI/check-rollup для `fcfd0f658ef...` не подтверждены через API.

Доступное historical evidence из репозитория:

- `docs/agent-work/pr46-ci-current-status.md`: ранее PR #46 был `OPEN`, `draft=true`, base `main`, head `codex/factory-autonomy-pwa-billing`, checks green для более раннего head.
- `docs/agent-work/github-pr-ci-primary-proof.md`: ранее authenticated REST proof показывал PR #46 `open`, `draft=true`, `mergeable_state=clean`, base `main`, head `codex/factory-autonomy-pwa-billing`; CI green для head `8222c179...`.
- Текущий git proof важнее для SHA: `refs/pull/46/head` уже указывает на `fcfd0f658ef...`, поэтому старые CI-документы нельзя считать свежим CI для нынешнего head.

## Live Control Plane

Команда `python3 ops/kolibri-dispatch nodes` показала:

| node_id | role status | health | fresh | active_task | capabilities summary |
| --- | --- | --- | --- | --- | --- |
| `main` | available | `online` | true | none | orchestrator, implementation, review, read_only_probe |
| `primary-candidate` | executing this task | `online` | true | `KOL-PRIMARY-DEVELOPMENT-CONTROL-RERUN-20260629` | primary, control-standby, orchestrator, implementation, review, read_only_probe, generic_implementation, generic_review |
| `qjns` | available | `online` | true | none | read_only_probe, implementation, review, qa, agent-host |
| `new` | available | `online` | true | none | review, read_only_probe, generic_review |
| `9fts` | not registered in `/v1/nodes` | blocker | n/a | n/a | legacy dispatch map has SSH entry, but live Control Plane does not list the node |

Legacy direct SSH probes for `new` and `9fts` through `kolibri-home` failed from this runtime because hostname `kolibri-home` did not resolve. Это не доказывает падение самих nodes: `new` свежий в Control Plane через mesh API namespace; `9fts` требует отдельного registration/heartbeat recovery.

## Машинные поручения

### main: Координатор очереди и Telegram

Task: `KOL-MAIN-CONTROL-PLANE-READONLY-AUDIT-20260629`.

Поручение: выполнить легкий `read_only_probe`, затем отдельным follow-up проверить `/health`, `/v1/nodes`, compact `/v1/tasks`, stale leases и один активный Telegram long-polling owner. Не мутировать очередь, Redis, PR, деплой или Telegram delivery без отдельного approval.

Acceptance:

- Artifact содержит node_id `main`, hostname, agent_id, heartbeat и `status=completed`.
- Есть summary counts по queued/running/waiting_review/failed/dead_letter без полного тяжелого scan.
- Нет FormulaLM/model benchmark.

### primary-candidate: Оператор primary-разработки

Task: `KOL-PRIMARY-DEVELOPMENT-CONTROL-RERUN-20260629`.

Поручение: держать PR #46 branch control, обновлять evidence по `origin/main`, `refs/pull/46/head`, CI, draft/ready blocker и dispatch follow-ups. До появления authenticated GitHub access не менять PR state и не выполнять merge/ready-for-review.

Acceptance:

- `docs/agent-work/primary-development-control-20260629.md` актуален.
- Есть blocker по `gh`/GitHub auth, если access отсутствует.
- Есть хотя бы один отправленный safe follow-up или explicit unsafe blocker.

### qjns: Инженер runtime qjns

Task candidate: `KOL-QJNS-RUNTIME-PREFLIGHT-20260629`.

Поручение: read-only preflight runtime: проверить git/node/npm/python/codex availability, writable artifact root, disk/RAM, ability to run lightweight tests, and Mimo/bootstrap blockers. Не делать install, deploy, queue surgery или benchmark без отдельного envelope.

Acceptance:

- Artifact с точными версиями и blockers.
- Проверен только read-only/runtime surface.
- Нет FormulaLM/model benchmark.

### new: Ревизор результатов

Task candidate: `KOL-NEW-RESULTS-REVIEW-QUEUE-20260629`.

Поручение: review-only audit свежих `docs/agent-work/*` по PR #46, PWA/QA blockers, waiting_review artifacts и release readiness. Так как `new` сейчас без permission packs в Control Plane, начинать с `read_only_probe` или review task без write_worktree, пока permissions не выданы.

Acceptance:

- Список документов, которые подтверждают или блокируют PR-ready.
- Явный status: `CI_UNKNOWN_FOR_CURRENT_HEAD` или authenticated `CI_GREEN/CI_FAIL`.
- Нет queue mutation, GitHub mutation, deploy, FormulaLM/model benchmark.

### 9fts: Разбор зависших Telegram задач

Task candidate: `KOL-9FTS-REGISTRATION-AND-TELEGRAM-STUCK-AUDIT-20260629`.

Поручение: сначала восстановить или подтвердить Control Plane registration/heartbeat для node_id `9fts`; только после fresh heartbeat выполнить read-only audit зависших Mimo/Telegram tasks. Не убивать процессы, не чистить Redis/spool и не отправлять Telegram без evidence и approval.

Acceptance:

- `/v1/nodes` показывает `9fts` fresh или artifact объясняет registration blocker.
- Если node недоступен, указаны hostname/proxy/DNS blockers без секретов.
- Нет FormulaLM/model benchmark.

## FormulaLM safety

FormulaLM/model benchmark не запускался. Любые FormulaLM действия разрешены только remote guarded task с preflight/blocker artifacts; Mac/control surface для benchmark запрещен.

## Проверки

Выполнено/запланировано для финального gate:

```bash
git status --short --branch
git rev-parse origin/main origin/codex/factory-autonomy-pwa-billing HEAD
git merge-base origin/main origin/codex/factory-autonomy-pwa-billing
git rev-list --left-right --count origin/main...origin/codex/factory-autonomy-pwa-billing
git ls-remote origin 'refs/pull/46/head' 'refs/pull/46/merge'
python3 ops/kolibri-dispatch doctor
python3 ops/kolibri-dispatch nodes
python3 -m json.tool ops/envelopes/KOL-MAIN-CONTROL-PLANE-READONLY-AUDIT-20260629.json >/dev/null
python3 ops/kolibri-dispatch submit --file ops/envelopes/KOL-MAIN-CONTROL-PLANE-READONLY-AUDIT-20260629.json
git diff --check -- docs/agent-work/primary-development-control-20260629.md ops/envelopes/KOL-MAIN-CONTROL-PLANE-READONLY-AUDIT-20260629.json
```

## Result reference

Primary artifact: `docs/agent-work/primary-development-control-20260629.md`.

Follow-up envelope: `ops/envelopes/KOL-MAIN-CONTROL-PLANE-READONLY-AUDIT-20260629.json`.

Follow-up Control Plane task id: `KOL-MAIN-CONTROL-PLANE-READONLY-AUDIT-20260629`.

Follow-up result_reference: `/var/lib/kolibri-agent/artifacts/KOL-MAIN-CONTROL-PLANE-READONLY-AUDIT-20260629/KOL-MAIN-CONTROL-PLANE-READONLY-AUDIT-20260629-attempt-1/result.json`.
