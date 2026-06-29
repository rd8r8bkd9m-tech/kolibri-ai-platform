# Control Plane stuck task sweep

Дата: 2026-06-29
Ветка: `codex/factory-autonomy-pwa-billing`

## Цель

Фабрика должна не только видеть задачи, но и возвращать в работу процессы,
которые числятся активными, но не дают heartbeat. Это закрывает часть
требования: "если агент не дает heartbeat или не показывает прогресс в течение
лимита, control plane обязан остановить/пометить задачу и передать ее другому
агенту".

## Изменения

- Добавлен `TASK_HEARTBEAT_STALE_AFTER`, по умолчанию `LEASE_DURATION * 2`.
- Добавлен `sweep_stuck_tasks(limit, stale_after)`:
  - читает только lease-index (`leased`, `running`, `review`);
  - считает возраст `heartbeat_at`;
  - для stale heartbeat выставляет `error_type=stuck_no_heartbeat`;
  - если retry budget есть, переводит задачу через `retry_scheduled` обратно в
    `queued`;
  - если retry budget исчерпан, переводит задачу в `dead_letter`;
  - пишет `attempt_history` со статусом `stuck_no_heartbeat` или
    `dead_letter_stuck`.
- Добавлен endpoint:

```text
POST /v1/tasks/sweep-stuck
```

- Добавлена CLI-команда:

```bash
ops/kolibri-dispatch sweep-stuck --limit 20 --stale-after-seconds 3600 --timeout 20
```

## Live deploy evidence

Main server: `root@10.99.0.2`
Service: `kolibri-factory-control.service`

После deploy:

```json
{
  "status": "ok",
  "redis": "PONG",
  "queue_backend": "redis"
}
```

Rebuild индекса:

```json
{
  "indexed": 690,
  "missing": 0,
  "states": {
    "cancelled": 19,
    "completed": 407,
    "dead_letter": 24,
    "failed": 147,
    "queued": 67,
    "running": 1,
    "waiting_review": 25
  }
}
```

Безопасный live sweep с порогом 3600 секунд:

```json
{
  "task_total": 690,
  "lease_index_total": 1,
  "checked": 1,
  "stuck": 0,
  "requeued_total": 0,
  "dead_lettered_total": 0,
  "scan_truncated": false,
  "stale_after_seconds": 3600
}
```

Текущая единственная `running` задача:

```json
{
  "task_id": "KOL-PRODUCT-QA-E2E-20260629-6d0317c5-home",
  "state": "running",
  "lease_owner": "home:agent-host-home",
  "attempt": 2,
  "max_retries": 2,
  "updated_at": "2026-06-29T07:34:03.745866+00:00"
}
```

## Локальные проверки

```bash
/tmp/kolibri-p0-venv/bin/python -m pytest -q \
  tests/test_factory_runtime_queue_contracts.py \
  tests/test_factory_runtime.py
```

Результат: `18 passed`.

```bash
python3 -m py_compile \
  ops/factory_control.py \
  ops/kolibri-dispatch \
  tests/test_factory_runtime_queue_contracts.py \
  tests/test_factory_runtime.py
git diff --check
```

Результат: passed.

## Следующий шаг

Подключить `sweep-stuck` к watchdog/cron с осторожным threshold и отдельным
отчетом в Telegram, чтобы фабрика сама лечила зависшие lease-задачи без ручного
сканирования Redis.
