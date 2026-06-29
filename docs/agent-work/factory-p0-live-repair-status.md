# Статус P0 восстановления фабрики

Дата: 2026-06-29  
Ответственный контур: Codex main coordinator + Kolibri Factory

## Короткий вывод

Фабрика снова выполняет новые задачи через свежий `main` worker, но еще не
работает на целевых 80% мощности. Исправлены два P0-блокера runtime:

1. `main` запускал старый `kolibri-agent-host`, который не поддерживал
   `generic_implementation`.
2. `GET /v1/tasks?summary=1&compact=1&limit=N` отдавал слишком тяжелый payload
   и зависал на истории задач.

## Что сделано

- Обновлен `/usr/local/bin/kolibri-agent-host` на `main` из текущего
  `ops/agent_host.py`.
- Перед заменой создан backup установленного agent host.
- `kolibri-agent-host.service` перезапущен и остался `active`.
- Повторная задача
  `KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629` принята Control Plane, взята
  `main:agent-host-main` и находится в `running` с живым heartbeat.
- Обновлен `/usr/local/bin/kolibri-factory-control` на Control Plane.
- Перед заменой создан backup установленного Control Plane binary.
- `kolibri-factory-control.service` перезапущен и остался `active`.
- Быстрый endpoint `/v1/agent-messages` включен и отвечает 200.
- Compact summary переведен на быстрый `queue_prefix` snapshot.

## Проверки после rollout

```text
GET /health
status=ok, redis=PONG

GET /v1/tasks?summary=1&compact=1&limit=5
queue_length=71
queue_returned=5
tasks_returned=5
summary_scope=queue_prefix
queue_truncated=true
tasks_truncated=true

GET /v1/agent-messages?target=all&limit=5
status=200, messages=[]

GET /v1/tasks/KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629
state=running
lease_owner=main:agent-host-main
error=null
```

Локальные проверки:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile ops/factory_control.py tests/test_factory_runtime_queue_contracts.py
/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_runtime_queue_contracts.py
git diff --check
```

Результат: `5 passed`, `git diff --check` чистый.

## Что еще не готово

- `server-kfrm` остается stale и еще не подтвержден как fresh executor.
- Большая часть зарегистрированных узлов stale; целевые 80% мощности пока не
  достигнуты.
- Очередь содержит 71 task, сейчас нужен controlled drain/recovery, а не
  массовый запуск без наблюдаемости.
- P0 app unblock task еще выполняется; результат надо забрать после completion.

## Следующий шаг

1. Дождаться результата `KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629`.
2. Восстановить `server-kfrm` через безопасный runtime rollout.
3. После fresh heartbeat на `server-kfrm` повторно отправить тяжелые QA/app
   задачи именно на него.
4. Коммитить локальные runtime/docs изменения и синхронизировать PR #46.
