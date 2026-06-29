# Rollout-план Factory Runtime: пул 6 агентов

Дата: 2026-06-29
Роль: `factory_runtime_sre`
Цель: развернуть и удерживать рабочий контур фабрики с целевым пулом 6
готовых субагентов/серверных Agent Host, автоматическим закрытием завершенных
исполнителей, Control Plane envelopes, отчетностью в GitHub Project и целевой
загрузкой 80%.

## Инварианты

- Remote-first: вся работа входит через `POST /v1/tasks` или
  `ops/kolibri-dispatch submit --file <envelope.json>`.
- Control Plane не читает node-local файлы; результат передается как
  `result_reference`, `result_path`, PR/branch и артефакты.
- Agent Host работает через systemd, регистрируется в
  `/v1/nodes/register`, поддерживает heartbeat через
  `/v1/nodes/<node_id>/heartbeat` и берет работу через `/v1/tasks/lease`.
- Завершенный субагент не остается в активном пуле: политика
  `completed_subagent_policy=close_after_artifact_handoff`.
- Целевой пул: 6 свежих, не-draining исполнителей с capability
  `generic_implementation` и permission pack `full_autonomy`.
- Целевая загрузка: 80% от пула 6, то есть 5 занятых lease и 1 резервный
  исполнитель для SRE/review/аварийного перехвата.
- Stale node не получает новые lease. По умолчанию stale threshold берется из
  `FACTORY_NODE_STALE_AFTER`, текущий кодовой default: 120 секунд.

## Операционная модель

Активными считаются задачи в состояниях `leased`, `running`,
`waiting_review`, `review`. Закрытыми считаются `completed`, `failed`,
`cancelled`, `dead_letter`.

Ready-agent входит в пул, если:

- `health=online`;
- `fresh=true`;
- `draining=false`;
- есть `generic_implementation` или нужная task capability;
- есть permissions для envelope, для полного автономного контура это
  `permission_pack=full_autonomy` или `permission:*`/`permissions=["*"]`;
- нет stale `active_task`, указывающего на terminal task.

Steady state:

- `ready_pool == 6`;
- `busy_target == 5`;
- `reserve == 1`;
- `stale_nodes == 0`;
- `queue` содержит следующие work envelopes, но не разгоняет busy выше 6.

## Rollout

### 0. Снимок перед изменениями

Выполнить с Control Plane host или из доверенного SRE окружения:

```bash
git status --short
curl -fsS http://10.99.0.2:9101/health
curl -fsS http://10.99.0.2:9101/v1/nodes
curl -fsS 'http://10.99.0.2:9101/v1/tasks?summary=1&compact=1'
curl -fsS 'http://10.99.0.2:9101/v1/agent-messages?target=all&limit=20'
```

Выходные критерии:

- Control Plane отвечает `status=ok`.
- Redis queue backend отвечает.
- Текущие чужие изменения в worktree зафиксированы как известный риск, но не
  перетираются.
- Есть список fresh/stale nodes, active tasks, terminal tasks и queue length.

### 1. Развернуть runtime-контракт

Проверить, что на Agent Host используется стандартный профиль:

```text
KOLIBRI_AGENT_CAPABILITIES=read_only_probe,generic_implementation,review,image_generation,mesh_node,permission:*
KOLIBRI_AGENT_PERMISSIONS=*
KOLIBRI_AGENT_PERMISSION_PACKS=full_autonomy
KOLIBRI_MAX_INFLIGHT=1
KOLIBRI_HEARTBEAT_INTERVAL=10
KOLIBRI_LEASE_REFRESH=20
```

Для новых или восстановленных серверов применять golden bootstrap:

```bash
KOLIBRI_FACTORY_CONTROL_URLS=http://10.99.0.2:9101 \
KOLIBRI_BOOTSTRAP_RESTART_JITTER=60 \
sudo -E ops/bootstrap_factory_node.sh
```

Для существующих узлов запускать rollout через Control Plane tasks, а не через
ручную настройку каждого сервера. Базовый runtime envelope уже есть:

```bash
ops/kolibri-dispatch submit --file ops/envelopes/KOL-CODEX-CLI-ROLLOUT-20260629.json
```

Выходные критерии:

- Каждый кандидат возвращает node id, версию runner, auth status без секретов и
  путь к артефакту.
- `codex --help` и `codex --version` проверены на узле или возвращен blocker
  artifact.
- В result payload нет токенов, `auth.json`, локальных секретов и приватных
  логов.

### 2. Обработать stale nodes

Сначала определить stale:

```bash
curl -fsS http://10.99.0.2:9101/v1/nodes \
  | jq '.nodes[] | select(.fresh != true or .health == "stale") | {node_id, health, heartbeat_age_seconds, active_task, active_task_state, draining}'
```

Для каждого stale node:

1. Включить drain, чтобы узел не получил новый lease после восстановления:

```bash
curl -fsS -X POST http://10.99.0.2:9101/v1/nodes/<node_id>/drain \
  -H 'content-type: application/json' \
  -d '{"drain": true}'
```

2. Если `active_task_state` terminal, считать agent slot закрытым и не держать
   его в active pool.
3. Если lease истек, дать Control Plane requeue через следующий
   `/v1/tasks/lease`; не клонировать задачу вручную без idempotency key.
4. Восстановить Agent Host стандартным deployment/bootstrap путем и дождаться
   fresh heartbeat.
5. Снять drain только после read-only probe.

Для `server-kfrm` использовать существующий probe envelope:

```bash
ops/kolibri-dispatch submit --file ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json
```

Выходные критерии:

- `stale_nodes == 0` для кандидатов в пул 6.
- У каждого восстановленного узла есть fresh heartbeat после probe.
- Нет `active_task_terminal=true` у ready nodes.

### 3. Сформировать целевой пул 6

Выбрать 6 свежих кандидатов, отсортированных по ресурсу и надежности:

```bash
curl -fsS http://10.99.0.2:9101/v1/nodes \
  | jq '.nodes[]
    | select(.fresh == true and .draining == false)
    | select((.capabilities // []) | index("generic_implementation"))
    | {node_id, hostname, health, heartbeat_age_seconds, capabilities, ram, disk}'
```

Назначить роли на задачи, а не на серверные личности. Минимальный пул для
первого rollout:

```text
1. factory_sre: runtime/watchdog, stale nodes, queue health.
2. principal_engineer: runtime/contracts/deploy fixes.
3. qa_lead: independent checks and product/factory smoke.
4. docs_steward: reports/runbooks/GitHub Project hygiene.
5. product_director: task slicing and acceptance control.
6. reviewer: reserve/review/emergency lane.
```

Первые 5 слотов могут брать рабочие lease. Шестой слот остается fresh reserve
или берет только короткие SRE/review задачи, если busy падает ниже 5.

### 4. Подавать Control Plane envelopes

Каждый rollout task должен иметь явный `task_id`, `idempotency_key`, `kind`,
`goal`, `acceptance`, `source`, `role_slot` и `permission_pack`.

Шаблон:

```json
{
  "task_id": "KOL-RUNTIME-POOL6-<ROLE>-20260629",
  "idempotency_key": "runtime-pool6:<role>:2026-06-29",
  "kind": "generic_implementation",
  "required_capability": "generic_implementation",
  "permission_pack": "full_autonomy",
  "runner": "codex",
  "role_slot": "<role>",
  "role_goal": "<role-specific objective>",
  "goal": "<single executable goal>",
  "acceptance": [
    "Result includes branch/PR or explicit blocker artifact",
    "Result includes exact verification commands and outputs summary",
    "No secrets or local-only paths are exposed to owner-facing channels",
    "If blocked, task reports missing dependency and next safe action"
  ],
  "verification_commands": [
    "python3 -m compileall -q ops/agent_host.py ops/factory_control.py"
  ],
  "create_review_on_complete": true,
  "review_node": "new",
  "max_retries": 2,
  "source": {
    "kind": "manual_control_plane",
    "requested_by": "factory_runtime_sre",
    "requested_at": "2026-06-29T00:00:00+03:00"
  }
}
```

Подача:

```bash
ops/kolibri-dispatch submit --file <envelope.json>
```

Canary порядок:

1. Один `read_only_probe` на восстановленный/новый узел.
2. Один короткий `generic_implementation` на `factory_sre`.
3. Расширить до 3 параллельных задач.
4. Расширить до target busy 5 при ready pool 6.

### 5. Auto-close completed agents

Закрывать agent slot автоматически, когда выполнены все условия:

- task state стал `completed`;
- есть `result_reference` или `result.result_path`;
- если был PR, есть `pull_request_url`/`pr_url` или создан review task;
- опубликован `task_completed` в `/v1/agent-messages`;
- GitHub Project item переведен в `Done` или `Review`, если требуется PR-review;
- node heartbeat после завершения уже не показывает этот task как активный.

Команда для поиска закрываемых задач:

```bash
curl -fsS 'http://10.99.0.2:9101/v1/tasks?compact=1&state=completed' \
  | jq '.tasks[] | {task_id, kind, lease_owner, result_reference, updated_at}'
```

Если node продолжает репортить terminal task как `active_task`, выполнить:

1. не считать этот slot busy;
2. дождаться следующего node heartbeat;
3. если terminal `active_task` остается больше 2 heartbeat intervals, завести
   SRE blocker item и перезапустить Agent Host штатным deployment путем;
4. не создавать duplicate task без idempotency key.

Top-up правило после auto-close:

```text
if ready_pool >= 6 and busy_active < 5:
  submit next queued envelope until busy_active == 5
if busy_active > 5:
  pause non-urgent submissions; reserve only review/SRE
```

### 6. GitHub Project reporting

GitHub Project является внешним операционным экраном. Каждый Control Plane task
должен иметь item или обновление item со следующими полями:

```text
Title: <task_id> <role_slot> <short goal>
Status: Queue | Running | Review | Done | Blocked | Dead
Role: role_slot
Node: lease_owner/node_id
Control Plane State: queued/leased/running/review/completed/failed/...
Branch: result.branch
PR: result.pull_request_url
Result: result_reference
Last Heartbeat: heartbeat_at / node heartbeat age
Utilization: busy_active/ready_pool
Blocker: error_type/error summary
```

Обновлять GitHub Project:

- при создании envelope;
- при переходе в `leased/running`;
- при `completed/failed/dead_letter`;
- каждые 15 минут публиковать compact summary.

Если точный project number не задан в окружении, SRE action не падает, а
создает blocker artifact:

```text
missing GITHUB_PROJECT_OWNER/GITHUB_PROJECT_NUMBER; Control Plane state is source of truth, GitHub Project sync pending
```

Минимальный отчет владельцу:

```text
Pool: ready 6, busy 5, reserve 1, stale 0
Queue: <queue_length>
Completed closed: <n>
Blocked: <task_id/error_type>
Next: <next envelope or restore action>
```

### 7. Utilization loop

Запускать каждые 5 минут или event-driven после terminal transition:

```text
1. Read /health.
2. Read /v1/nodes.
3. Read /v1/tasks?summary=1&compact=1.
4. close_completed_agents().
5. mark stale nodes drained.
6. ready_pool = fresh non-draining capable agents.
7. busy_active = leased + running + waiting_review + review.
8. if ready_pool < 6: restore/bootstrap nodes before adding work.
9. if ready_pool >= 6 and busy_active < 5: submit next envelopes.
10. if busy_active > 5: pause non-urgent submissions.
11. sync GitHub Project and owner summary.
```

SLO для первого суток:

- Control Plane `/health`: 99% успешных checks.
- Heartbeat age p95 для ready nodes: меньше 30 секунд.
- Stale ready nodes: 0.
- Lease expiry without retry success: 0 для canary, максимум 1 для full rollout.
- Completed auto-close latency: меньше 2 минут после `completed`.
- GitHub Project lag: меньше 15 минут.
- Utilization: 4-5 busy из 6, кратковременный максимум 6 только для review/SRE
  surge.

## Rollback

Rollback включается при любом из условий:

- Control Plane health fail больше 2 минут.
- Больше 1 stale node в пуле 6 после восстановления.
- Две подряд lease expiry на одном runtime profile.
- В result/log payload обнаружен секрет.
- GitHub Project sync вводит владельца в заблуждение по статусам.

Действия:

```bash
# 1. Остановить новые lease на проблемном узле.
curl -fsS -X POST http://10.99.0.2:9101/v1/nodes/<node_id>/drain \
  -H 'content-type: application/json' \
  -d '{"drain": true}'

# 2. Остановить подачу новых non-urgent envelopes.
# 3. Дать running задачам завершиться или отменить только явно выбранные.
curl -fsS -X POST http://10.99.0.2:9101/v1/tasks/<task_id>/cancel \
  -H 'content-type: application/json' \
  -d '{"reason": "runtime rollout rollback"}'

# 4. Вернуть предыдущий runtime/deployment profile штатным deploy путем.
# 5. Зафиксировать incident в GitHub Project и owner summary.
```

После rollback целевой safe mode:

- ready pool не ниже 3;
- busy не выше 2;
- stale nodes drained;
- все failed/dead_letter имеют blocker artifact.

## Проверки готовности

Локальные contract checks перед rollout PR/deploy:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q ops/agent_host.py ops/factory_control.py ops/mesh_control_bridge.py ops/telegram_gateway.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_factory_runtime_contracts.py \
  tests/test_factory_autonomy_contracts.py \
  tests/test_factory_agent_messages.py
```

Control Plane smoke:

```bash
curl -fsS http://10.99.0.2:9101/health
curl -fsS http://10.99.0.2:9101/v1/nodes \
  | jq '[.nodes[] | select(.fresh == true and .draining == false)] | length'
curl -fsS 'http://10.99.0.2:9101/v1/tasks?summary=1&compact=1'
```

Pool acceptance:

```text
ready_pool == 6
busy_active in [4, 5]
reserve >= 1
stale_nodes == 0
active_task_terminal == 0
completed tasks have result_reference or blocker artifact
GitHub Project updated within 15 minutes
```

Owner handoff line:

```text
Factory runtime rollout is green: ready 6, busy 5, reserve 1, stale 0, auto-close active, GitHub Project synced, next envelopes queued.
```
