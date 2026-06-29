# Control Plane task list fast path

Дата: 2026-06-29
Статус: выполнено и задеплоено

## Проблема

`GET /v1/tasks?limit=3` мог не отвечать за 8 секунд, потому что unfiltered listing вызывал полный scan по `task_ids` и загружал сотни задач до применения `limit`.

Это мешало пульту управления, watchdog-диагностике и owner-facing статусам: Control Plane превращался в тяжёлый архивный запрос вместо быстрого операционного среза.

## Исправление

- Добавлен fast path `operational_task_sample()`.
- Unfiltered `/v1/tasks` теперь использует:
  - `queue_prefix(limit + offset)`
  - `active_task_ids()`
  - dedupe по task id
  - `MGET` только по возвращаемым task ids
- Полный scan через `all_task_ids()` больше не нужен для обычного оперативного листинга.
- `state=` фильтр продолжает использовать state index.

## Проверки

Локально:

```text
/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_runtime_queue_contracts.py tests/test_factory_runtime.py tests/test_factory_autonomy_contracts.py tests/test_factory_lease_watchdog.py tests/test_telegram_gateway.py tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py tests/test_agent_host_telegram_chat.py
104 passed
```

```text
python3 -m py_compile ops/factory_control.py
git diff --check
passed
```

Live на `10.99.0.2`:

До:

```text
curl -m 8 http://10.99.0.2:9101/v1/tasks?limit=3
timeout after 8 seconds
```

После:

```text
elapsed_seconds=0.674
source=queue_active_index
tasks_scanned=3
tasks_returned=3
queue_total=68
active_candidate_total=26
```

## Деплой

- `/usr/local/bin/kolibri-factory-control` обновлён.
- `kolibri-factory-control.service` перезапущен.
- `GET /v1/health`: `status=ok`, `redis=PONG`, `queue_backend=redis`.

## Файлы

- `ops/factory_control.py`
- `tests/test_factory_runtime_queue_contracts.py`

## Значение для фабрики

Control Plane теперь быстрее отдаёт рабочий срез задач для UI, Telegram, watchdog и orchestration. Это снижает риск ситуации, когда мониторинг сам перегружает центральную систему управления.

