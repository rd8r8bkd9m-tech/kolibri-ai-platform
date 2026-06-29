# API Kolibri AI

Дата сверки: 2026-06-29. Источник истины для этого документа - код в
`backend/`, `ops/`, `frontend/` и контрактные тесты. Endpoint считается
реализованным только если он объявлен в коде или проксируется явным правилом.

## 1. Базовые контуры

| Контур | База | Код |
| --- | --- | --- |
| Product backend | `/api/*`, `/ws/*` | `backend/main.py`, `backend/routes_v1.py`, `backend/billing.py` |
| Control Plane | `KOLIBRI_FACTORY_CONTROL_URL`, по умолчанию `http://10.99.0.2:9101` для CLI и Telegram | `ops/factory_control.py`, `ops/kolibri-dispatch`, `ops/telegram_gateway.py` |
| Frontend/PWA | `/` и `/app`; локально API уходит на `http://<host>:8000`, в проде на текущий origin | `frontend/src/config.js`, `frontend/src/App.jsx` |
| Telegram report CLI | `python3 ops/telegram_gateway.py --send-report ...` | `ops/telegram_gateway.py` |

## 2. Product backend API

FastAPI приложение объявлено в `backend/main.py`. CORS сейчас разрешает все
origins, methods и headers.

### 2.1 Health, providers, models

| Метод | Endpoint | Назначение | Ответ |
| --- | --- | --- | --- |
| `GET` | `/api/health` | Health backend и статусы AI providers | `{"status":"ok","provider_status":...}` |
| `GET` | `/api/providers` | Статусы providers | объект из `AIProviderManager.get_status()` |
| `GET` | `/api/models` | Каталог моделей и system prompt | `{"models":[...],"system_prompt":"..."}` |

### 2.2 Chat и WebSocket

`POST /api/chat`

Тело:

```json
{
  "messages": [{"role": "user", "content": "Привет"}],
  "model": "auto",
  "provider": "mimo",
  "temperature": 0.7,
  "max_tokens": 2048,
  "system_prompt": null,
  "enable_thinking": false
}
```

Поведение:

- rate limit: 60 запросов в 60 секунд на IP;
- cache key строится из `model` и `messages`;
- при cache hit ответ содержит `cached: true`;
- при cache miss вызывает `AIProviderManager.generate(...)`.

Ответ успешного запроса: результат provider плюс `cached: false`.

`WS /ws/chat`

Клиент отправляет JSON:

```json
{
  "messages": [{"role": "user", "content": "Привет"}],
  "model": "auto",
  "temperature": 0.7,
  "max_tokens": 2048,
  "enable_thinking": false
}
```

Если `messages` пустой, сервер отправляет `{"error":"No messages provided"}`.
Иначе отправляет результат `AIProviderManager.generate(...)` одним сообщением.

### 2.3 Conversations

| Метод | Endpoint | Запрос | Ответ |
| --- | --- | --- | --- |
| `POST` | `/api/conversations?title=<title>` | query `title`, default `New Chat` | `{"id":"conv_<timestamp>","title":"..."}` |
| `GET` | `/api/conversations` | нет | массив `{id,title,created_at,updated_at}` |
| `GET` | `/api/conversations/{conv_id}/messages` | path `conv_id` | массив `{role,content,provider,created_at}` |
| `DELETE` | `/api/conversations/{conv_id}` | path `conv_id` | `{"deleted":true}` |

### 2.4 TTS, search, tools, pipeline

| Метод | Endpoint | Тело | Ответ |
| --- | --- | --- | --- |
| `POST` | `/api/tts` | `{"text":"...","voice":"en-US-AriaNeural"}` | результат `TTSEngine.synthesize` |
| `GET` | `/api/tts/voices` | нет | результат `TTSEngine.list_voices` |
| `POST` | `/api/search` | `{"query":"...","num_results":5}` | `{"results":[...]}` |
| `POST` | `/api/tools` | `{"message":"...","tools":[...]}` | результат `AIProviderManager.tool_call` |
| `POST` | `/api/pipeline` | `PipelineRequest` из `backend/pipeline.py` | `run_pipeline(...).model_dump()` |
| `GET` | `/api/pipeline/health` | нет | результат `pipeline_health()` |

### 2.5 Factory status facade

`GET /api/factory/status` и alias `GET /cluster/status`.

Backend читает Control Plane через `KOLIBRI_FACTORY_CONTROL_URL`
(`http://control.kolibri.internal:9101` по умолчанию для backend) и вызывает:

- `GET /v1/health`;
- `GET /v1/nodes`;
- best-effort `GET /v1/tasks`.

Успешный ответ содержит:

```json
{
  "status": "online",
  "source": "control-plane",
  "generated_at": "2026-06-29T00:00:00+00:00",
  "control_plane": {"url": "...", "status": "ok", "queue_backend": "redis", "redis": "PONG"},
  "total_nodes": 0,
  "online_nodes": 0,
  "free_ram_gb": 0,
  "total_ram_gb": 0,
  "avg_cpu_percent": 0,
  "queue_size": 0,
  "task_states": {},
  "nodes": {},
  "node_list": []
}
```

При ошибке facade возвращает HTTP 503 и degraded payload с
`control_plane.status = "unavailable"`.

### 2.6 `/api/v1/*` compatibility routes

`backend/routes_v1.py` объявляет совместимые v1 endpoints:

| Метод | Endpoint | Ответ/поведение |
| --- | --- | --- |
| `GET` | `/api/v1/ai/models` | `models=[{"name":"mimo-auto","description":"Auto mode"}]` и system prompt |
| `GET` | `/api/v1/model/stats` | `{"status":"ok","models":["mimo-auto"],"active":"mimo-auto"}` |
| `POST` | `/api/v1/ai/chat` | читает `messages`, вызывает provider `mimo` |
| `POST` | `/api/v1/ai/chat/stream` | SSE: один `data: <result>` и `data: [DONE]` |
| `POST` | `/api/v1/ai/imagine` | заглушка `Image generation coming soon` |
| `POST` | `/api/v1/ai/vision/analyze` | заглушка `Vision analysis coming soon` |
| `POST` | `/api/v1/ai/demo/learn/text` | заглушка `Learning coming soon` |
| `GET` | `/api/v1/ai/quality/benchmark/history` | `{"history":[]}` |
| `GET` | `/api/v1/swarm/runtime/status` | `{"status":"active","nodes":4}` |
| `GET` | `/api/v1/ai/training/queue/status` | `{"queue":[]}` |
| `POST` | `/api/v1/swarm/runtime/start` | `{"status":"started"}` |
| `POST` | `/api/v1/swarm/runtime/refresh` | `{"status":"refreshed"}` |
| `POST` | `/api/v1/swarm/runtime/run` | `{"status":"ok"}` |
| `POST` | `/api/v1/swarm/runtime/ingest/text` | `{"status":"ok"}` |
| `POST` | `/api/v1/swarm/runtime/ingest/url` | `{"status":"ok"}` |
| `POST` | `/api/v1/swarm/runtime/kpack/export` | `{"status":"ok"}` |
| `POST` | `/api/v1/swarm/runtime/kpack/import` | `{"status":"ok"}` |

### 2.7 Proxy routes

`backend/main.py` проксирует любые методы `GET`, `POST`, `PUT`, `DELETE`,
`PATCH`, `OPTIONS`, `HEAD` для этих prefixes:

| Prefix frontend/backend | Upstream | Rewrite |
| --- | --- | --- |
| `/api/knowledge...` | `http://10.99.0.3:8002` | strip `/api/knowledge`, add `/rag` |
| `/api/agent...` | `http://10.99.0.4:8003` | strip `/api/agent`, add `/agent` |
| `/api/inference...` | `http://10.99.0.5:8001` | strip `/api/inference`, add `/inference` |
| `/cluster...` | `http://127.0.0.1:9001` | strip `/cluster` |

Исключение: `/api/v1/*` не проксируется fallback-handler'ом и при
несовпадении с объявленными v1 routes получает 404.

### 2.8 Детерминированные сметы: текущая граница

На дату сверки public HTTP endpoints `/api/estimates/*` в FastAPI не объявлены.
Расчетное ядро находится в `backend/estimate_engine.py`, а P0-контракт для
будущих endpoints описан в
`docs/agent-work/deterministic-estimates-p0-contract.md`.

Методологическое правило: одинаковый canonical request при одинаковых версиях
прайсбука, регионального профиля, коэффициентов и расчетных правил должен
давать одинаковый estimate JSON. Точность 98-99% нельзя заявлять как свойство
API без frozen benchmark dataset и опубликованных метрик прогона.

## 3. Billing API

Billing router подключен с prefix `/api/billing`. Данные хранятся в SQLite:
`KOLIBRI_DB_PATH` или `/opt/kolibri-ai/data/kolibri.db`.

Переменные окружения:

| Переменная | Назначение |
| --- | --- |
| `TBANK_API_URL` | T-Банк API base, default `https://securepay.tinkoff.ru/v2` |
| `TBANK_TERMINAL_KEY` | terminal key |
| `TBANK_PASSWORD` | password для token generation и проверки notification |
| `KOLIBRI_PUBLIC_URL` / `PUBLIC_URL` | база для `NotificationURL`, `SuccessURL`, `FailURL` |
| `KOLIBRI_BILLING_ADMIN_TOKEN` | required token для charge-due |
| `KOLIBRI_PLAN_SOLO_KOPEKS` | цена Solo, default `490000` |
| `KOLIBRI_PLAN_TEAM_KOPEKS` | цена Team, default `1490000` |
| `KOLIBRI_PLAN_STUDIO_KOPEKS` | цена Studio, default `3990000` |

### 3.1 `GET /api/billing/plans`

Ответ:

```json
{
  "provider": "tbank",
  "configured": false,
  "plans": [
    {
      "id": "solo",
      "name": "Solo",
      "amount_kopeks": 490000,
      "price_rub": "4 900",
      "interval": "month",
      "monthly_limit": "до 30 смет в месяц",
      "primary_use": "мастер или небольшой подрядчик",
      "highlights": ["AI-сметы", "КП и счет", "экспорт PDF"]
    }
  ]
}
```

`configured` истинно только если заданы `TBANK_TERMINAL_KEY` и
`TBANK_PASSWORD`.

### 3.2 `POST /api/billing/checkout`

Тело:

```json
{
  "plan_id": "team",
  "email": "client@example.com",
  "company": "Kolibri",
  "name": "Alex",
  "phone": "+79990000000"
}
```

Validation:

- `plan_id`: 2..32 символа, должен быть `solo`, `team` или `studio`;
- `email`: 5..160 символов и email pattern;
- `company`: до 120 символов;
- `name`: до 80 символов;
- `phone`: до 40 символов.

Если T-Банк не настроен, endpoint сохраняет запись в `billing_leads` и
возвращает:

```json
{
  "mode": "lead",
  "provider": "tbank",
  "configured": false,
  "message": "Заявка сохранена. Для оплаты подключите TBANK_TERMINAL_KEY и TBANK_PASSWORD."
}
```

Если T-Банк настроен, backend вызывает T-Банк `Init` с recurrent payment:

- `Recurrent: "Y"`;
- `PayType: "O"`;
- `DATA.OperationInitiatorType: "1"`;
- `NotificationURL: <public_base>/api/billing/tbank/notification`;
- `SuccessURL: <public_base>/?payment=success&order=<order_id>`;
- `FailURL: <public_base>/?payment=fail&order=<order_id>`.

Успешный ответ:

```json
{
  "mode": "payment",
  "provider": "tbank",
  "subscription_id": "sub_...",
  "order_id": "sub_team_...",
  "payment_id": "123",
  "payment_url": "https://..."
}
```

Ошибки:

- 404 `Unknown plan`;
- 502 при неуспешном или неполном ответе T-Банк.

### 3.3 `POST /api/billing/tbank/notification`

Callback принимает JSON или form payload. Token проверяется по алгоритму
T-Банк: все scalar поля кроме `Token`, плюс `Password`, сортировка ключей,
конкатенация значений, SHA-256.

Обязательные проверки:

- `Token` валиден;
- `OrderId` не пустой;
- `TerminalKey` присутствует;
- если задан `TBANK_TERMINAL_KEY`, `TerminalKey` должен совпадать;
- для успешных статусов `PaymentId` и `Amount` обязательны;
- `Amount` должен совпадать с суммой подписки.

Успешные статусы: `AUTHORIZED`, `CONFIRMED`, `COMPLETED` при
`Success=true`. Они активируют подписку, сохраняют `rebill_id`, период 30 дней
и `next_charge_at`.

Failed statuses: `REJECTED`, `CANCELED`, `DEADLINE_EXPIRED`,
`ATTEMPTS_EXPIRED`, `REVERSED`, `REFUNDED`. `REJECTED` переводит подписку в
`past_due`, остальные - в `canceled`.

Ответ при принятом payload: plain text `OK`.

### 3.4 `POST /api/billing/tbank/charge-due`

Header:

```http
X-Kolibri-Billing-Token: <KOLIBRI_BILLING_ADMIN_TOKEN>
```

Тело:

```json
{"limit": 20}
```

`limit` от 1 до 100. Endpoint выбирает active subscriptions с `rebill_id` и
`next_charge_at <= now`, вызывает T-Банк `Init` с
`DATA.OperationInitiatorType: "R"`, затем `Charge`.

Ответ:

```json
{
  "processed": 1,
  "results": [
    {"subscription_id": "sub_...", "charged": true, "response": {}}
  ]
}
```

Ошибки:

- 403 если admin token не настроен или header не совпал;
- 503 если T-Банк credentials не настроены.

## 4. Control Plane API

Control Plane реализован стандартной библиотекой Python в
`ops/factory_control.py`, хранит состояние в Redis namespace
`FACTORY_NAMESPACE` (`kolibri_factory` по умолчанию).

Переменные:

| Переменная | Default | Назначение |
| --- | --- | --- |
| `FACTORY_BIND` | `127.0.0.1` | bind address sidecar |
| `FACTORY_PORT` | `9101` | port sidecar |
| `FACTORY_REDIS_HOST` | `127.0.0.1` | Redis host |
| `FACTORY_REDIS_PORT` | `6379` | Redis port |
| `FACTORY_LEASE_DURATION` | `60` | lease TTL, seconds |
| `FACTORY_MAX_RETRIES` | `3` | retries by default |
| `FACTORY_NODE_STALE_AFTER` | `120` | heartbeat stale threshold |

Task states:

`queued`, `leased`, `running`, `waiting_review`, `review`, `completed`,
`failed`, `cancelled`, `retry_scheduled`, `dead_letter`.

Terminal states: `completed`, `failed`, `cancelled`, `dead_letter`.

### 4.1 Health

`GET /health` и `GET /v1/health`

Ответ:

```json
{
  "status": "ok",
  "redis": "PONG",
  "queue_backend": "redis",
  "time": "2026-06-29T00:00:00+00:00"
}
```

### 4.2 Nodes

`GET /v1/nodes`

Ответ:

```json
{"nodes": []}
```

Каждый node декорируется полями:

- `draining`;
- `heartbeat_age_seconds`;
- `fresh`;
- если heartbeat stale, `health` становится `stale`;
- при `active_task` добавляются `active_task_state` и `active_task_terminal`.

`POST /v1/nodes/register`

Тело:

```json
{
  "node_id": "main",
  "hostname": "host",
  "capabilities": ["generic_implementation"],
  "permissions": ["read_repo", "write_artifacts"],
  "permission_packs": ["implementation"],
  "pid": 123,
  "cpu": 10.5,
  "ram": {},
  "disk": {},
  "agent_id": "agent-main"
}
```

Ответ: сохраненная node card с `health: "online"` и текущим `heartbeat_at`.

`POST /v1/nodes/<node_id>/heartbeat`

Тело: partial node fields. Endpoint обновляет node, нормализует
`permissions` и `permission_packs`, ставит `health: "online"` и новый
`heartbeat_at`.

`POST /v1/nodes/<node_id>/drain`

Тело:

```json
{"drain": true}
```

Ответ:

```json
{"node_id":"main","draining":true}
```

### 4.3 Tasks

`POST /v1/tasks`

Тело - task envelope. Минимально Control Plane может принять почти любой JSON:
если `task_id` не задан, он создаст `KOL-TASK-<12 hex>`; если `kind` не задан,
ставит `read_only_probe`. Для desktop owner envelope контракт требует более
строгие поля: `task_id`, `kind`, `goal`, `acceptance`, `source`.

Пример:

```json
{
  "task_id": "KOL-DOCS-20260629",
  "idempotency_key": "docs:api-ru:2026-06-29",
  "kind": "generic_implementation",
  "goal": "Обновить API документацию",
  "acceptance": ["docs/API-RU.md создан"],
  "source": {"kind": "manual"},
  "required_capability": "generic_implementation",
  "permission_pack": "implementation",
  "max_retries": 1
}
```

Ответ HTTP 201: normalized task:

```json
{
  "task_id": "KOL-DOCS-20260629",
  "idempotency_key": "docs:api-ru:2026-06-29",
  "kind": "generic_implementation",
  "permission_pack": "implementation",
  "required_permissions": ["git_push", "network", "read_repo", "run_tests", "write_artifacts", "write_worktree"],
  "state": "queued",
  "attempt": 0,
  "max_retries": 1,
  "attempt_id": null,
  "lease_owner": null,
  "lease_until": null,
  "heartbeat_at": null,
  "result_reference": null,
  "result": null,
  "error_type": null,
  "error": null,
  "created_at": "...",
  "updated_at": "...",
  "envelope": {}
}
```

Idempotency: если `idempotency_key` уже указывает на существующую task, API
возвращает существующую task вместо создания новой.

`GET /v1/tasks`

Query:

- `state=<state>` - фильтр по state;
- `summary=1|true|yes` - вернуть summary;
- `compact=1|true|yes` - compact task shape;
- `limit=<n>` - ограничение после сортировки по `updated_at`/`created_at`.

Без `summary` ответ:

```json
{"tasks": [], "queue": []}
```

С `summary=1` ответ:

```json
{
  "summary": {
    "total": 0,
    "states": {},
    "active": []
  },
  "queue_length": 0
}
```

Compact task содержит:

`task_id`, `kind`, `state`, `target_node`, `required_capability`,
`permission_pack`, `required_permissions`, `attempt`, `max_retries`,
`lease_owner`, `lease_until`, `error_type`, `created_at`, `updated_at`.

`GET /v1/tasks/<task_id>`

Ответ: полная task или 404:

```json
{"error":"task_not_found","task_id":"..."}
```

`POST /v1/tasks/lease` worker-only

Тело:

```json
{
  "node_id": "main",
  "agent_id": "agent-main",
  "capabilities": ["generic_implementation"],
  "permissions": ["read_repo", "write_artifacts"]
}
```

Поведение:

- сначала requeue expired leases;
- если node в drain, HTTP 204;
- выбирает первую compatible task из Redis queue;
- учитывает `target_node`/`required_node`, `allowed_nodes`,
  `required_capability`, `required_permissions`;
- ставит `state: leased`, увеличивает `attempt`, создает `attempt_id`,
  `lease_owner`, `lease_until`, `heartbeat_at`, `granted_permissions`.

Если подходящих задач нет: HTTP 204.

`POST /v1/tasks/<task_id>/heartbeat` worker-only

Тело может содержать:

```json
{
  "state": "running",
  "pid": 123,
  "worktree": "...",
  "branch": "...",
  "log_paths": []
}
```

Если task не terminal, endpoint обновляет state (`running` по умолчанию),
`heartbeat_at`, продлевает `lease_until`, сохраняет runtime metadata.

`POST /v1/tasks/<task_id>/complete` worker-only

Тело:

```json
{
  "result": {"result_path": "...", "pull_request_url": "https://..."},
  "result_reference": "..."
}
```

Если envelope содержит `create_review_on_complete` и result не содержит PR URL,
task переходит в `waiting_review`; иначе в `completed`. При наличии PR и
`create_review_on_complete` создается review task с kind `review_pr`.

Ответ:

```json
{"task": {}, "review_task": null}
```

`POST /v1/tasks/<task_id>/annotate`

Тело может быть произвольным result patch:

```json
{
  "result": {"note": "review ok", "pull_request_url": "https://..."},
  "result_reference": "..."
}
```

Endpoint merge'ит `result`, обновляет `result_reference` и `heartbeat_at`.
Если task была `waiting_review` и появился PR URL, state становится
`completed`, затем создается review task.

`POST /v1/tasks/<task_id>/fail` worker-only

Тело:

```json
{
  "error_type": "runtime_error",
  "error": "trace",
  "result": {},
  "result_reference": "...",
  "retry": true
}
```

Если retry budget не исчерпан и `retry` не false, task проходит
`retry_scheduled` и возвращается в `queued`; иначе становится `failed`.

`POST /v1/tasks/<task_id>/cancel`

Тело:

```json
{"reason": "cancelled by operator"}
```

Endpoint удаляет task из queue, ставит `state: cancelled`,
`cancel_requested_at`, `lease_until: null`. Reason сейчас не сохраняется
отдельным полем.

### 4.4 Agent messages

`POST /v1/agent-messages`

Тело:

```json
{
  "message_id": "MSG-custom",
  "sender": "main",
  "recipients": ["all"],
  "kind": "status",
  "topic": "docs",
  "task_id": "KOL-DOCS-20260629",
  "body": "Документация обновлена",
  "artifacts": []
}
```

`sender` может также прийти как `from`, `recipients` - как `to`. Если
recipients пустые, используется `["all"]`. Сообщение публикуется в feed `all`
и во все recipient feeds, каждый feed хранит до 500 сообщений.

Ответ HTTP 201: normalized message с `created_at`.

`GET /v1/agent-messages?target=all&limit=50`

Ответ:

```json
{"target":"all","messages":[]}
```

## 5. Control Plane CLI

### 5.1 `ops/kolibri-dispatch`

Новый режим CLI работает с Control Plane. База:

```bash
ops/kolibri-dispatch --control-url http://10.99.0.2:9101 <command>
```

`--control-url` можно ставить после command; CLI переносит его в global args.
Default: `KOLIBRI_FACTORY_CONTROL_URL` или `http://10.99.0.2:9101`.

Команды:

| Команда | HTTP calls | Назначение |
| --- | --- | --- |
| `doctor` | `GET /health`; SSH checks для известных nodes | диагностика repo, gh auth, binaries, nodes |
| `nodes` | `GET /v1/nodes` | вывести node inventory |
| `submit --file envelope.json` | `POST /v1/tasks` | отправить envelope; без `--file` читает stdin |
| `status [task_id] [--state s] [--limit n] [--full]` | `GET /v1/tasks...` или `GET /v1/tasks/<task_id>` | summary/list/detail |
| `collect <task_id>` | `GET /v1/tasks/<task_id>` | вывести `task_id`, `state`, `result_reference`, `result` |
| `cancel <task_id> [--reason "..."]` | `POST /v1/tasks/<task_id>/cancel` | отменить task |
| `drain <node_id> --enable/--disable` | `POST /v1/nodes/<node_id>/drain` | включить или снять drain |

Если CLI запущен без subcommand, включается legacy SSH one-shot режим. Для
новой документации и автоматизации предпочтителен режим `submit/status/...`.

### 5.2 Telegram gateway report CLI

`ops/telegram_gateway.py` одновременно long-polling gateway и report sender.
Report sender активируется флагом `--send-report`, отправляет Markdown/text
файл владельцу в Telegram и завершает процесс.

Команда:

```bash
TELEGRAM_BOT_TOKEN=... \
python3 ops/telegram_gateway.py \
  --state-file /var/lib/kolibri-telegram-gateway/state.json \
  --send-report docs/agent-work/status.md \
  --report-chat-id 123456 \
  --report-title "Статус фабрики" \
  --report-agent "Супервизор" \
  --report-status "готово" \
  --report-summary "Короткое резюме"
```

Аргументы и env:

| CLI | Env default | Назначение |
| --- | --- | --- |
| `--control-url` | `KOLIBRI_FACTORY_CONTROL_URL` или `http://10.99.0.2:9101` | primary Control Plane URL для gateway mode |
| `--control-urls` | `KOLIBRI_FACTORY_CONTROL_URLS` или `KOLIBRI_FACTORY_CONTROL_URL` | comma-separated failover URLs |
| `--state-file` | `TELEGRAM_GATEWAY_STATE` или `/var/lib/kolibri-telegram-gateway/state.json` | state с offset, tracked tasks, owner chat id, memory |
| `--poll-timeout` | `TELEGRAM_POLL_TIMEOUT` или `25` | long polling timeout |
| `--send-report` | нет | путь к report file, включает one-shot sender |
| `--report-chat-id` | `TELEGRAM_REPORT_CHAT_ID` | явный Telegram chat id |
| `--report-title` | `TELEGRAM_REPORT_TITLE` | тема письма |
| `--report-agent` | `TELEGRAM_REPORT_AGENT` | ответственный |
| `--report-status` | `TELEGRAM_REPORT_STATUS` | статус |
| `--report-summary` | `TELEGRAM_REPORT_SUMMARY` | краткое резюме |

Report letter format:

```text
Тема: <title>
Дата: <UTC ISO timestamp>
Ответственный: <agent или Kolibri automation>
Статус: <status или отчёт>

Кратко:
<sanitized summary>

Документ:
<sanitized report file>
```

Если `--report-chat-id` не задан, sender ищет `owner_chat_id` в state, затем
первый `chat_id` в `tracked`. Если chat id не найден, выбрасывает RuntimeError
с текстом про `TELEGRAM_REPORT_CHAT_ID`.

Ограничение Telegram chunk: `REPORT_CHUNK_LIMIT = 3600`. Длинный текст
делится по параграфам, затем по строкам/пробелам. Для нескольких частей
добавляется prefix `<title> (i/n)`.

Sanitizer скрывает:

- строки с `-----begin`, `private key`, `authorization:`, `cookie:`,
  `set-cookie:`;
- значения ключей `token`, `secret`, `password`, `passwd`, `api_key`,
  `access_token`, `refresh_token`, `client_secret`;
- приватные пути под `/var/lib/kolibri-agent`, `/run/secrets`,
  `/etc/kolibri`, `/tmp`.

Успешный stdout:

```json
{"chat_id":123456,"event":"telegram_report_sent","parts":1,"title":"Статус фабрики"}
```

## 6. Telegram gateway task contracts

Gateway принимает только private messages от user id из `TELEGRAM_OWNER_IDS`.
Неавторизованным отвечает `Доступ запрещен.`

Gateway может:

- отвечать сразу на часть owner prompts;
- создать factory task через `POST /v1/tasks`;
- создать chat task;
- создать image generation task;
- отслеживать task state и отправлять owner-safe updates.

### 6.1 Work task envelope

`build_task_envelope(...)`:

```json
{
  "task_id": "TG-<YYYYMMDDHHMMSS>-<message_id>-<ascii_suffix>",
  "idempotency_key": "telegram:<chat_id>:<message_id>",
  "kind": "owner_remote_task",
  "required_capability": "generic_implementation",
  "review_node": "new",
  "create_review_on_complete": false,
  "branch": "agent/<task_id>/impl/<ascii_suffix>",
  "base_branch": "main",
  "base_ref": "origin/main",
  "max_retries": 1,
  "objective": "<owner text>",
  "project_path": null,
  "conversation_context": {},
  "source": {
    "kind": "telegram",
    "message_id": 1,
    "chat_id": 100,
    "user_id": 100,
    "accepted_at": "..."
  }
}
```

Env overrides:

- `TELEGRAM_TASK_KIND`;
- `TELEGRAM_TASK_CAPABILITY`;
- `TELEGRAM_TASK_MAX_RETRIES`;
- `TELEGRAM_TASK_NODE`;
- `TELEGRAM_OWNER_PROJECT_PATH`.

### 6.2 Chat task envelope

`build_chat_envelope(...)`:

```json
{
  "task_id": "TGCHAT-<YYYYMMDDHHMMSS>-<message_id>-<ascii_suffix>",
  "idempotency_key": "telegram-chat:<chat_id>:<message_id>",
  "kind": "owner_remote_task",
  "required_capability": "generic_implementation",
  "max_retries": 1,
  "message": "<owner text>",
  "objective": "<owner-safe answer prompt>",
  "runner": "codex",
  "factory_snapshot": {},
  "target_node": "primary-candidate",
  "source": {"kind": "telegram", "...": "..."}
}
```

Env overrides: `TELEGRAM_CHAT_KIND`, `TELEGRAM_CHAT_CAPABILITY`,
`TELEGRAM_CHAT_RUNNER`, `TELEGRAM_CHAT_NODE`.

### 6.3 Image task envelope

`build_image_envelope(...)`:

```json
{
  "task_id": "TGIMG-<YYYYMMDDHHMMSS>-<message_id>-<ascii_suffix>",
  "idempotency_key": "telegram-image:<chat_id>:<message_id>",
  "kind": "telegram_image_generation",
  "required_capability": "generic_implementation",
  "max_retries": 1,
  "message": "<owner text>",
  "prompt": "<owner text>",
  "objective": "<image result prompt>",
  "runner": "image",
  "factory_snapshot": {},
  "target_node": "primary-candidate",
  "source": {"kind": "telegram", "...": "..."}
}
```

Env overrides: `TELEGRAM_IMAGE_KIND`, `TELEGRAM_IMAGE_CAPABILITY`,
`TELEGRAM_IMAGE_MAX_RETRIES`, `TELEGRAM_IMAGE_RUNNER`, `TELEGRAM_IMAGE_NODE`.

## 7. PWA и frontend contracts

### 7.1 Runtime API base

`frontend/src/config.js`:

- `IS_LOCAL`: hostname `localhost` или `127.0.0.1`;
- local `API_BASE`: `http://<hostname>:8000`;
- production `API_BASE`: empty string, то есть current origin;
- local `WS_HOST`: `<hostname>:8000`;
- production `WS_HOST`: `window.location.host`.

### 7.2 Frontend API calls

`frontend/src/App.jsx` вызывает:

| Поверхность | Endpoint | Статус backend |
| --- | --- | --- |
| providers | `GET /api/providers` | реализован |
| chat WS | `WS /ws/chat` | реализован |
| chat fallback | `POST /api/chat` | реализован |
| factory panel | `GET /api/factory/status` | реализован |
| billing plans | `GET /api/billing/plans` | реализован |
| billing checkout | `POST /api/billing/checkout` | реализован |
| documents list | `GET /api/knowledge` | прокси на RAG upstream; не локальный FastAPI handler |
| document upload | `POST /api/knowledge/upload` | прокси на RAG upstream; не локальный FastAPI handler |
| document search | `POST /api/knowledge/search` | прокси на RAG upstream; не локальный FastAPI handler |

Payment return contract:

- `/?payment=success&order=<order_id>` показывает сообщение, что оплата
  принята и подписка активируется после callback Т-Банка;
- `/?payment=fail&order=<order_id>` показывает сообщение о незавершенном
  платеже;
- после обработки query frontend делает `history.replaceState` на pathname.

### 7.3 PWA service worker

Регистрация: `frontend/public/pwa-register.js` регистрирует
`/service-worker.js` со scope `/`.

Cache name: `kolibri-ai-pwa-v1`.

App shell cache:

- `/`;
- `/manifest.webmanifest`;
- `/kolibri.svg`;
- `/icons/apple-touch-icon.png`;
- `/icons/icon-192.png`;
- `/icons/icon-512.png`.

Fetch policy:

- только `GET`;
- внешние origins не перехватываются;
- пути `/api*` и `/ws*` не перехватываются;
- navigation пытается `fetch`, затем fallback на cached `/`, затем plain text
  `Kolibri AI is offline.` с HTTP 503;
- static destinations `font`, `image`, `manifest`, `script`, `style`,
  `worker` работают cache-first.

PWA status hook:

- если service workers не поддерживаются: `не поддерживается`;
- если `display-mode: standalone` или `navigator.standalone`: `установлено`;
- иначе: `готово к установке`;
- initial state: `проверка`.

## 8. Desktop-control contracts

`backend/desktop_control_contracts.py` - контрактный модуль и validator для
desktop-control MVP. Он не подключен в FastAPI router и сам по себе не создает
HTTP endpoints.

### 8.1 Owner Control Plane endpoints

Desktop owner surface может использовать:

| Метод | Endpoint | Confirmation |
| --- | --- | --- |
| `GET` | `/health` | нет |
| `GET` | `/v1/health` | нет |
| `GET` | `/v1/nodes` | нет |
| `POST` | `/v1/nodes/<node_id>/drain` | да |
| `GET` | `/v1/tasks?summary=1&compact=1` | нет |
| `GET` | `/v1/tasks?state=<state>&limit=<n>` | нет |
| `GET` | `/v1/tasks/<task_id>` | нет |
| `POST` | `/v1/tasks` | да |
| `POST` | `/v1/tasks/<task_id>/cancel` | да |
| `POST` | `/v1/tasks/<task_id>/annotate` | нет |
| `GET` | `/v1/agent-messages?target=all&limit=<n>` | нет |
| `POST` | `/v1/agent-messages` | нет |

### 8.2 Worker-only endpoints

Desktop app не должна вызывать эти endpoints как owner actions:

- `POST /v1/tasks/lease`;
- `POST /v1/tasks/<task_id>/heartbeat`;
- `POST /v1/tasks/<task_id>/complete`;
- `POST /v1/tasks/<task_id>/fail`;
- `POST /v1/nodes/register`;
- `POST /v1/nodes/<node_id>/heartbeat`.

### 8.3 Roadmap endpoints

Эти endpoints описаны как roadmap и сейчас не реализованы в
`ops/factory_control.py`:

- `GET /v1/filesystem`;
- `GET /v1/tasks/<task_id>/artifacts`;
- `POST /v1/tasks/<task_id>/requeue`;
- `GET /v1/events`.

### 8.4 Desktop facade placeholders

`DESKTOP_FACADE_PLACEHOLDERS` перечисляет будущие backend facade paths
`/api/desktop-control/*`. В текущем FastAPI app они не подключены. До появления
router'а их нельзя считать публичным API:

- `GET /api/desktop-control/health`;
- `GET /api/desktop-control/nodes`;
- `GET /api/desktop-control/tasks`;
- `GET /api/desktop-control/tasks/<task_id>`;
- `POST /api/desktop-control/tasks`;
- `POST /api/desktop-control/tasks/<task_id>/cancel`;
- `POST /api/desktop-control/tasks/<task_id>/annotate`;
- `POST /api/desktop-control/nodes/<node_id>/drain`;
- `GET /api/desktop-control/agent-messages`;
- `POST /api/desktop-control/agent-messages`.

### 8.5 Envelope validation и redaction

Required envelope fields для desktop submit:

```text
task_id, kind, goal, acceptance, source
```

Rules:

- `acceptance` должен быть list;
- `source` должен быть object;
- secret markers запрещены: `.env`, `BEGIN PRIVATE KEY`,
  `BEGIN RSA PRIVATE KEY`, `cookies.sqlite`, `auth.json`, `id_rsa`,
  `id_ed25519`;
- dangerous permission packs: `full_autonomy`, `shell`, `admin`, `root`
  требуют явного owner confirmation;
- owner summary sanitizer скрывает token/password/cookie markers и локальные
  пути под `/Users`, `/home`, `/tmp`, `/var/folders`, `/opt/kolibri-ai`,
  `/root`.

`PROJECT_SYNC_PENDING = "Project sync: pending"` - канонический текст
degraded Project sync state.

## 9. Не подтверждено как реализованный API

Эти контракты встречаются в specs/frontend, но не являются отдельными
реализованными handlers в текущем backend:

- `/api/desktop-control/*` - placeholder contracts, router не подключен;
- `/v1/filesystem`, `/v1/tasks/<task_id>/artifacts`,
  `/v1/tasks/<task_id>/requeue`, `/v1/events` - roadmap Control Plane;
- `/api/knowledge*` - не локальные FastAPI handlers; только proxy route на RAG
  upstream `http://10.99.0.3:8002/rag...`.
