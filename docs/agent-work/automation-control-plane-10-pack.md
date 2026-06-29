# Automation Control Plane 10-pack

Дата: 2026-06-29  
Роль: `automation_control_plane_architect`  
Статус: архитектура и рекомендации; automations этим документом не создаются

## 1. Назначение

Второй контур контроля нужен не для замены Control Plane, а для наблюдения,
раннего ремонта безопасных сбоев и быстрой эскалации Владиславу или
оператору. Источник факта остается прежним:

- Control Plane хранит task state, leases, node heartbeats и result references;
- Agent Host работает в node-local worktree/artifacts;
- GitHub Project показывает owner-facing операционную картину;
- automation не должна читать node-local файлы напрямую и не должна обходить
  Control Plane через ad hoc SSH как основной путь.

Этот пакет описывает 10 процессов автоматизации:

1. фабрика целиком;
2. Ubuntu QA;
3. Control Plane failover;
4. очередь и leases;
5. ноды;
6. GitHub CI;
7. GitHub Project;
8. subagent pool;
9. billing;
10. FormulaLM remote-only.

## 2. Общие инварианты

- Все work tasks входят через `POST /v1/tasks` или
  `ops/kolibri-dispatch submit --file <envelope.json>`.
- Legacy SSH-режим `ops/kolibri-dispatch` без subcommand считается
  совместимостью, а не основным repair path.
- Health/read checks могут выполняться часто; write/repair actions должны быть
  идемпотентными, с audit artifact и коротким owner-facing summary.
- Stale threshold берется из `FACTORY_NODE_STALE_AFTER`; текущий default в коде
  `120` секунд.
- Lease duration берется из `FACTORY_LEASE_DURATION`; текущий default `60`
  секунд.
- Standard Agent Host heartbeat: `KOLIBRI_HEARTBEAT_INTERVAL=10`,
  `KOLIBRI_LEASE_REFRESH=20`.
- Для фабрики целевой режим: ready pool 6, busy 4-5, reserve минимум 1,
  stale ready nodes 0.
- Нельзя публиковать секреты, raw auth files, приватные логи, investor contacts
  и node-local paths в owner-facing каналах без явной debug-просьбы.

## 3. Базовые команды чтения

```bash
export KOLIBRI_CONTROL_URL="${KOLIBRI_CONTROL_URL:-http://10.99.0.2:9101}"

curl -fsS "$KOLIBRI_CONTROL_URL/health"
curl -fsS "$KOLIBRI_CONTROL_URL/v1/nodes"
curl -fsS "$KOLIBRI_CONTROL_URL/v1/tasks?summary=1&compact=1&limit=200"
curl -fsS "$KOLIBRI_CONTROL_URL/v1/agent-messages?target=all&limit=50"

ops/kolibri-dispatch --control-url "$KOLIBRI_CONTROL_URL" nodes
ops/kolibri-dispatch --control-url "$KOLIBRI_CONTROL_URL" status --limit 200
```

`/v1/filesystem` в документации отмечается как target/planned contract. Если
endpoint еще не реализован в конкретной сборке, automation должна фиксировать
`filesystem_check: planned_or_unavailable`, а не считать весь Control Plane
упавшим.

## 4. Матрица 10 automations

| # | Automation | Тип | Период | Главный сигнал | Safe repair |
| --- | --- | --- | --- | --- | --- |
| 1 | `kolibri-factory-health-sentinel` | heartbeat | 30 секунд | `/health`, nodes, tasks summary, agent feed | owner summary, P0 blocker, pause non-urgent submissions |
| 2 | `kolibri-ubuntu-qa-watchdog` | cron | 1 час и перед rollout | remote Ubuntu preflight через Control Plane | QA issue/envelope, read-only probe |
| 3 | `kolibri-control-plane-failover-guard` | heartbeat | 30 секунд | primary/secondary `/health` | temporary read failover, P0 blocker |
| 4 | `kolibri-queue-lease-watchdog` | cron | 5 минут | queued/running/retry/dead_letter, expired leases | drain stale lease owners, wait controlled requeue |
| 5 | `kolibri-node-fleet-watchdog` | heartbeat | 1 минута | heartbeat age, fresh, draining, capabilities | drain stale, request probe after recovery |
| 6 | `kolibri-github-ci-auto-fix-monitor` | cron | 1 час и on PR update | GitHub checks/logs | rerun transient job, draft blocker/fix PR |
| 7 | `kolibri-github-project-sync-guard` | cron | 15 минут | Project item lag vs Control Plane | issue/PR comments, Project sync pending |
| 8 | `kolibri-subagent-pool-supervisor` | cron | 15 минут | target_active_subagents=6 | artifact handoff, close completed, replacement from backlog |
| 9 | `kolibri-billing-ops-guardian` | cron | 15 минут checks, daily charge window | plans, checkout mode, notifications, charge-due | pause schedule, create billing blocker/follow-up |
| 10 | `kolibri-formulalm-remote-only-guard` | heartbeat + preflight gate | before every FormulaLM task and every 10 минут during benchmark | OS/runtime/node/preflight artifacts | block Darwin/local run, require remote probe |

## 5. Automation cards

### 5.1 `kolibri-factory-health-sentinel`

Назначение: общий сторож фабрики. Он отвечает на вопрос: принимает ли фабрика
работу, есть ли свежие ноды, не копится ли очередь, есть ли публично понятный
статус.

Тип: heartbeat.  
Период: каждые 30 секунд; owner summary каждые 15 минут или при P0.

Команды и проверки:

```bash
curl -fsS "$KOLIBRI_CONTROL_URL/health"
curl -fsS "$KOLIBRI_CONTROL_URL/v1/nodes"
curl -fsS "$KOLIBRI_CONTROL_URL/v1/tasks?summary=1&compact=1&limit=200"
curl -fsS "$KOLIBRI_CONTROL_URL/v1/agent-messages?target=all&limit=20"
curl -fsS "http://127.0.0.1:8000/api/factory/status"
```

Проверять:

- `/health.status == ok`;
- Redis отвечает как queue backend;
- `ready_pool >= 3` в degraded safe mode и `ready_pool == 6` в штатном режиме;
- `busy_active <= ready_pool`;
- `stale_nodes == 0` для ready pool;
- нет массовых `dead_letter`;
- owner-facing `/api/factory/status` возвращает JSON, а не traceback.

Безопасные repair actions:

- создать compact incident summary в issue/PR comment или Control Plane
  artifact;
- перевести non-urgent submissions в pause flag на уровне automation state;
- если конкретная stale node продолжает получать lease, включить drain через
  документированный endpoint:

```bash
ops/kolibri-dispatch --control-url "$KOLIBRI_CONTROL_URL" drain <node_id> --enable
```

- отправить read-only probe только по заранее подготовленному envelope.

Escalation:

- P0 сразу, если `/health` падает больше 2 минут или owner-facing API падает
  traceback;
- P1, если ready pool ниже 6 больше 15 минут, но остается safe capacity;
- P2, если есть единичные nonblocking warnings без влияния на очередь.

Нельзя без подтверждения:

- перезапускать Control Plane/Redis/systemd services;
- сбрасывать Redis keys, чистить queue или `dead_letter`;
- отменять running tasks пачкой;
- менять `FACTORY_*` env values;
- использовать SSH dispatcher вместо Control Plane path.

### 5.2 `kolibri-ubuntu-qa-watchdog`

Назначение: следить, что remote Ubuntu nodes готовы к Agent Host, Codex/runtime,
тестам, сборкам и не требуют ручного ремонта перед rollout.

Тип: cron.  
Период: каждый час; обязательно перед bootstrap/rollout/release decision.

Команды и проверки:

```bash
ops/kolibri-dispatch --control-url "$KOLIBRI_CONTROL_URL" nodes
ops/kolibri-dispatch --control-url "$KOLIBRI_CONTROL_URL" status --limit 50
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q ops/agent_host.py ops/factory_control.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_factory_runtime_contracts.py \
  tests/test_factory_autonomy_contracts.py \
  tests/test_factory_agent_messages.py
```

Remote Ubuntu preflight должен приходить как artifact от ноды, а не как
локальная догадка:

- `uname -a`;
- `platform.system`;
- `python3 --version`;
- `git --version`;
- `codex --version` или blocker;
- disk/RAM;
- service status без секретов;
- artifact directory и manifest.

Безопасные repair actions:

- создать QA blocker issue с node id, симптомом и безопасным следующим шагом;
- отправить `read_only_probe` на восстановленную ноду;
- подготовить bootstrap/rollout envelope для оператора;
- пометить ноду `draining=true`, если heartbeat stale или runtime profile
  явно не соответствует стандарту.

Escalation:

- P0, если Ubuntu QA блокирует investor/demo или все Linux runners недоступны;
- P1, если один runtime profile ломает rollout;
- P2, если требуется плановое обновление документации или bootstrap notes.

Нельзя без подтверждения:

- делать `apt upgrade`, менять kernel, reboot/shutdown;
- менять users, sudoers, firewall, SSH keys;
- устанавливать модельные runtime на production node вне Control Plane task;
- запускать heavy/model tests на Mac;
- считать отсутствие preflight artifact успешной проверкой.

### 5.3 `kolibri-control-plane-failover-guard`

Назначение: проверять primary/secondary Control Plane endpoints и удерживать
корректный failover behavior для Agent Host, Telegram gateway и dispatchers.

Тип: heartbeat.  
Период: каждые 30 секунд; reconciliation report каждые 5 минут.

Команды и проверки:

```bash
for url in ${KOLIBRI_FACTORY_CONTROL_URLS//,/ }; do
  curl -fsS "$url/health"
  curl -fsS "$url/v1/tasks?summary=1&compact=1&limit=20"
done
```

Проверять:

- primary отвечает `/health`;
- secondary endpoints из `KOLIBRI_FACTORY_CONTROL_URLS` отвечают или явно
  отсутствуют в конфигурации;
- task summary не расходится между endpoints;
- Agent Host env содержит comma-separated failover list, а не одиночный stale
  URL;
- automation не пишет в два расходящихся Control Plane одновременно.

Безопасные repair actions:

- для read-only мониторинга временно переключить порядок URL внутри самой
  automation state;
- остановить подачу новых non-urgent envelopes при split-brain symptoms;
- создать P0 blocker с primary/secondary health matrix;
- рекомендовать failover switch, но не выполнять инфраструктурное переключение
  без подтверждения.

Escalation:

- P0, если primary недоступен больше 2 минут или endpoints расходятся по queue
  state;
- P1, если failover URL отсутствует у части Agent Host profiles;
- P2, если нужно обновить документацию/env example.

Нельзя без подтверждения:

- менять DNS, Cloudflare, routing, firewall, systemd env на серверах;
- промотировать secondary в primary;
- рестартовать Control Plane или Redis;
- выполнять writes на secondary при непонятном источнике факта;
- менять `KOLIBRI_FACTORY_CONTROL_URLS` в production.

### 5.4 `kolibri-queue-lease-watchdog`

Назначение: следить за очередью, retry budget, lease expiry и задачами, которые
застряли между `leased`, `running`, `retry_scheduled` и `dead_letter`.

Тип: cron.  
Период: каждые 5 минут; event-driven после terminal transition.

Команды и проверки:

```bash
ops/kolibri-dispatch --control-url "$KOLIBRI_CONTROL_URL" status --limit 200
curl -fsS "$KOLIBRI_CONTROL_URL/v1/tasks?summary=1&compact=1&limit=200"
curl -fsS "$KOLIBRI_CONTROL_URL/v1/tasks?state=dead_letter&compact=1&limit=50"
```

Проверять:

- queue length trend;
- задачи в `leased/running/review` с `lease_until` в прошлом;
- repeated `lease_expired` по одному node/runtime profile;
- `dead_letter` без blocker artifact;
- duplicate task attempts без idempotency key;
- `waiting_review` без PR/result.

Безопасные repair actions:

- дать Control Plane самому requeue expired lease через следующий
  `/v1/tasks/lease`, не клонируя task вручную;
- включить drain на stale lease owner;
- создать blocker report для `dead_letter` с error type, attempt history и
  next action;
- подать заранее approved read-only probe или review task, если acceptance это
  требует.

Escalation:

- P0, если queue не движется больше 10 минут при available ready pool;
- P1, если `dead_letter` касается release/demo/payment/factory runtime;
- P2, если проблема одиночная и есть retry path.

Нельзя без подтверждения:

- чистить очередь, удалять Redis keys или менять attempt counters;
- массово отменять running tasks;
- вручную создавать duplicate tasks без idempotency key;
- менять `FACTORY_LEASE_DURATION` или `FACTORY_MAX_RETRIES`;
- считать `retry_scheduled` успехом без конечного artifact.

### 5.5 `kolibri-node-fleet-watchdog`

Назначение: следить за fleet health: heartbeat freshness, draining, capability
profile, permission packs, ресурсами и active task hygiene.

Тип: heartbeat.  
Период: каждая 1 минута; deep report каждые 15 минут.

Команды и проверки:

```bash
curl -fsS "$KOLIBRI_CONTROL_URL/v1/nodes" \
  | jq '.nodes[] | {node_id, health, fresh, heartbeat_age_seconds, draining, active_task, active_task_state, active_task_terminal, capabilities, permission_packs, ram, disk}'
```

Проверять:

- `fresh=true` для ready pool;
- `heartbeat_age_seconds <= FACTORY_NODE_STALE_AFTER`;
- `draining=false` только для нод, которые можно нагружать;
- capability `generic_implementation` для основного пула;
- `permission_pack=full_autonomy` или `permission:*` для автономных задач;
- нет `active_task_terminal=true`;
- reserve node остается свободной при target busy 5/6.

Безопасные repair actions:

- включить drain на stale или misconfigured node;
- не считать terminal active task занятым слотом после artifact handoff;
- запланировать read-only probe после восстановления heartbeat;
- создать bootstrap envelope recommendation для новых нод.

Escalation:

- P0, если меньше 3 fresh нод или все capable nodes stale;
- P1, если ready pool меньше 6 больше 15 минут;
- P2, если capabilities/permission packs требуют планового rollout.

Нельзя без подтверждения:

- удалять node records из Control Plane;
- менять capabilities/permissions вручную в Redis;
- снимать drain до успешного read-only probe;
- reboot/reinstall/bootstrap node напрямую через SSH;
- назначать уникальные server personalities вместо role assignment per task.

### 5.6 `kolibri-github-ci-auto-fix-monitor`

Назначение: не давать красному CI зависать без владельца, blocker report или
исправления.

Тип: cron.  
Период: каждый час; дополнительно on PR/check update.

Команды и проверки:

```bash
gh auth status
gh pr list --repo "$KOLIBRI_REPO" --state open --json number,title,headRefName,isDraft,statusCheckRollup
gh run list --repo "$KOLIBRI_REPO" --limit 20
gh run view <run_id> --log-failed
```

Проверять:

- open PR с red/yellow checks;
- checks без явного owner comment;
- flaky/transient failures vs code failures;
- PR body содержит verification, risks, blockers;
- секреты не попали в logs/comments.

Безопасные repair actions:

- rerun явно transient job один раз;
- создать blocker comment с job URL, failure summary и next action;
- для своей automation-owned ветки подготовить минимальный fix commit/PR после
  локальных тестов;
- обновить Project item в `В работе` или `Заблокирована`.

Escalation:

- P0, если CI блокирует release/investor demo в ближайшие 24 часа;
- P1, если PR готов, но check красный из-за кода;
- P2, если flaky external issue и есть documented rerun.

Нельзя без подтверждения:

- merge PR;
- force push, rewrite history или откатывать чужие изменения;
- закрывать чужой PR/issue;
- менять GitHub Actions secrets, branch protections или required checks;
- публиковать raw failed logs с секретами.

### 5.7 `kolibri-github-project-sync-guard`

Назначение: удерживать GitHub Project как внешний экран владельца, не путая его
с источником runtime-факта.

Тип: cron.  
Период: каждые 15 минут; сразу после completed/failed/dead_letter.

Команды и проверки:

```bash
gh auth status
gh project view 2 --owner rd8r8bkd9m-tech --web
gh project item-list 2 --owner rd8r8bkd9m-tech --limit 100
ops/kolibri-dispatch --control-url "$KOLIBRI_CONTROL_URL" status --limit 200
```

Проверять:

- scopes `repo`, `workflow`, `project`, `read:org`;
- items без `Следующий отчёт`;
- `Заблокирована` без actionable blocker;
- Control Plane state vs Project status mapping;
- completed tasks без artifact/result/PR в Project;
- FormulaLM/billing/investor claims без evidence.

Безопасные repair actions:

- добавить issue/PR comment с `Project sync: pending`, если Project API
  недоступен;
- обновить owner-facing status fields при наличии artifact;
- создать issue для Control Plane blocker, если item отсутствует;
- оставить точный blocker с командой и stderr при `gh project` failure.

Escalation:

- P0, если Project показывает `Готово` для незакрытого P0 blocker;
- P1, если Project lag больше 15 минут по активному milestone;
- P2, если отсутствует необязательное поле или docs follow-up.

Нельзя без подтверждения:

- добавлять/переименовывать Project fields;
- массово архивировать items;
- переводить item в `Готово` без artifact/result/PR;
- публиковать investor private-only данные;
- закрывать issue/PR вместо автора задачи.

### 5.8 `kolibri-subagent-pool-supervisor`

Назначение: поддерживать 6 активных субагентов и не терять результаты
completed-субагентов перед закрытием.

Тип: cron.  
Период: каждые 15 минут.

Команды и проверки:

Проверки зависят от текущего runtime Codex/subagent API, но логика фиксирована:

```text
target_active_subagents = 6
completed_subagent_policy = close_after_artifact_handoff
replacement backlog = docs/subagent-pool.md
```

Проверять:

- сколько активных субагентов реально в работе;
- есть ли completed;
- у completed есть summary/artifact/file/PR/issue;
- replacement идет по backlog order;
- FormulaLM/model tasks не назначены Mac/local executor;
- GitHub Project отражает active/review/done/blocker.

Безопасные repair actions:

- сохранить краткий итог completed-субагента в отчет;
- закрыть completed только после artifact handoff;
- создать replacement из backlog, чтобы снова стало 6 active;
- если нет уверенности в artifact, не закрывать, а создать blocker.

Escalation:

- P0, если результат completed агента может быть потерян;
- P1, если active pool меньше 6 больше 15 минут;
- P2, если нужен новый backlog item или role catalog cleanup.

Нельзя без подтверждения:

- запускать больше 6 активных без отдельного rationale;
- закрывать in-progress или blocked агента без handoff;
- менять backlog order без причины;
- назначать FormulaLM/LLM benchmark локально на Mac;
- удалять artifacts, thread summaries или PR references.

### 5.9 `kolibri-billing-ops-guardian`

Назначение: следить за подписками, T-Банк readiness, fallback lead mode,
notification security и charge-due без риска случайных списаний.

Тип: cron.  
Период: каждые 15 минут read checks; charge-due только в отдельное дневное окно
и только при включенном billing schedule.

Команды и проверки:

```bash
curl -fsS "http://127.0.0.1:8000/api/billing/plans"
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider backend/tests/test_billing.py

curl -i -X POST "http://127.0.0.1:8000/api/billing/tbank/charge-due" \
  -H "content-type: application/json" \
  -d '{"limit":1}'
```

Последняя команда без `X-Kolibri-Billing-Token` должна вернуть `403`; это
безопасная negative check. Реальный charge-due требует admin token и отдельного
run window.

Проверять:

- `/plans.provider == tbank`;
- `/plans.configured` соответствует наличию credentials;
- fallback checkout не создает active subscription;
- notification token validation не обходит signature;
- charge-due без header возвращает `403`;
- charge-due без T-Банк credentials возвращает безопасный error;
- billing events не содержат публичных секретов.

Безопасные repair actions:

- при provider outage перевести billing item в `Заблокирована`;
- остановить billing schedule flag на уровне automation state при repeated
  charge failures;
- создать follow-up для fallback leads;
- подготовить sandbox verification checklist.

Escalation:

- P0, если есть риск неверной активации/списания или payment outage;
- P1, если T-Банк sandbox/notification не проходит перед запуском продаж;
- P2, если fallback leads требуют ручной обработки.

Нельзя без подтверждения:

- запускать реальные списания вне approved charge window;
- делать refund/cancel/manual activation;
- менять тарифы, суммы, fiscalization или legal text;
- менять `TBANK_*` credentials и admin token;
- считать `SuccessURL` доказательством оплаты.

### 5.10 `kolibri-formulalm-remote-only-guard`

Назначение: гарантировать, что FormulaLM/Qwen/model benchmarks выполняются
только на remote Linux factory nodes и дают честные artifacts.

Тип: preflight gate + heartbeat.  
Период: перед каждым FormulaLM task; каждые 10 минут во время long benchmark;
daily summary для R&D.

Команды и проверки:

```bash
ops/kolibri-dispatch --control-url "$KOLIBRI_CONTROL_URL" nodes
ops/kolibri-dispatch --control-url "$KOLIBRI_CONTROL_URL" status KOL-FORMULALM-REMOTE-BENCH-6H-20260629
curl -fsS "$KOLIBRI_CONTROL_URL/v1/agent-messages?target=all&limit=50"
```

Preflight artifact от executor должен содержать:

- `platform.system != Darwin`;
- Linux hostname/node id/task id;
- runtime type/version;
- model id;
- dataset version;
- pricebook version `kolibri-ru-2026q2-v1`;
- artifact directory;
- baseline и FormulaLM mode settings.

Проверять:

- envelope содержит `role_slot: formulalm_researcher`;
- envelope явно запрещает запуск на Mac;
- target node fresh, non-draining, Linux;
- нет дублирующего running benchmark для того же task;
- metrics разделяют `proven`, `inconclusive`, `blocked`;
- raw logs не публикуются без redaction.

Безопасные repair actions:

- если executor OS Darwin или preflight отсутствует, завершить как blocker
  artifact, не запускать benchmark;
- если целевая node stale, включить drain и запросить read-only probe;
- если runtime/model отсутствует, создать blocker artifact без synthetic
  metrics;
- после long benchmark обновить GitHub Project только ссылкой на sanitized
  report.

Escalation:

- P0, если benchmark запущен локально на Mac или есть fabricated metrics;
- P1, если remote runtime/model отсутствует перед investor/research milestone;
- P2, если dataset/metric expansion требует плановой R&D задачи.

Нельзя без подтверждения:

- запускать FormulaLM/Qwen/LLM benchmark на Mac;
- запускать nightly/heavy benchmark без отдельного owner approval;
- менять dataset/pricebook в середине сравнения;
- публиковать raw model logs, private prompts или secrets;
- объявлять FormulaLM доказанным без decision rules и artifacts.

## 6. Рекомендации по внедрению

1. Сначала создать все 10 automations в dry-run/report-only режиме на 24 часа.
2. Включать repair actions по одному: сначала `drain stale`, затем Project
   sync comments, затем CI rerun, затем subagent top-up.
3. Для каждого repair action хранить `automation_run_id`, input snapshot,
   command, result, owner-facing summary и rollback note.
4. Для P0 incidents писать GitHub-visible blocker и короткое сообщение
   владельцу без raw node paths.
5. Для любых write actions использовать allowlist команд; shell free-form
   запрещен.
6. Разнести schedules с jitter, чтобы все 10 процессов не били Control Plane в
   одну секунду.
7. Считать `Control Plane state` источником факта, а GitHub Project - экраном
   синхронизации.

## 7. Минимальный формат отчета automation

```markdown
Automation: kolibri-...
Run id: 2026-06-29T12:00:00+03:00/...
Status: green / degraded / blocked / repaired
Scope: factory / queue / billing / ...
Checks:
- command: ...
  result: ok / failed / skipped
Safe repair:
- action: ...
  result: done / skipped
Escalation:
- priority: P0/P1/P2/none
  reason: ...
Artifacts:
- issue/PR/result/report: ...
Next:
- next check at ...
```

## 8. Решения, требующие подтверждения Владислава

- Production failover switch Control Plane.
- Restart/rollback Control Plane, Redis, Agent Host fleet or billing services.
- Queue purge, Redis key mutation, dead-letter mass cancellation.
- Real billing charge/refund/manual subscription activation.
- GitHub Project schema changes and mass item archival.
- Merge, force push, branch deletion, protected branch changes.
- FormulaLM nightly/heavy benchmark or any local Mac model benchmark.
- Adding more than 6 active subagents or changing replacement backlog policy.
- Publishing raw logs, private investor/customer data or node-local paths.

