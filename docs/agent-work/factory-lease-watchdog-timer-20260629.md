# Factory lease watchdog timer

Дата: 2026-06-29
Ветка: `codex/factory-autonomy-pwa-billing`

## Цель

Перевести ручные операции `reap-expired` и `sweep-stuck` в регулярный
автоматический контур, чтобы Control Plane сам возвращал зависшие lease-задачи
в очередь или dead-letter без ручного запуска CLI.

## Добавлено

- `ops/factory_lease_watchdog.py`
  - проверяет `/v1/health`;
  - запускает `/v1/tasks/reap-expired`;
  - запускает `/v1/tasks/sweep-stuck`;
  - пишет JSON и Markdown отчеты;
  - работает только через Control Plane API, без прямого Redis и без OS-level
    kill процессов.
- `ops/systemd/kolibri-factory-lease-watchdog.service`
- `ops/systemd/kolibri-factory-lease-watchdog.timer`

## Live deploy evidence

Main server: `root@10.99.0.2`

Установлено:

```text
/usr/local/bin/kolibri-factory-lease-watchdog
/etc/systemd/system/kolibri-factory-lease-watchdog.service
/etc/systemd/system/kolibri-factory-lease-watchdog.timer
```

Ручной прогон:

```json
{
  "status": "ok",
  "redis": "PONG",
  "task_total": 690,
  "lease_index_total": 0,
  "expired": 0,
  "stuck": 0,
  "requeued_expired": 0,
  "requeued_stuck": 0,
  "dead_lettered_expired": 0,
  "dead_lettered_stuck": 0,
  "stale_after_seconds": 3600
}
```

Systemd timer:

```text
Active: active (waiting)
Trigger: Mon 2026-06-29 07:45:01 UTC
```

Systemd service:

```text
Active: inactive (dead)
ExecStart=/usr/local/bin/kolibri-factory-lease-watchdog (code=exited, status=0/SUCCESS)
```

Отчеты на сервере:

```text
/var/lib/kolibri-factory-control/watchdog/latest.json
/var/lib/kolibri-factory-control/watchdog/latest.md
```

## Локальные проверки

```bash
/tmp/kolibri-p0-venv/bin/python -m pytest -q \
  tests/test_factory_lease_watchdog.py \
  tests/test_factory_runtime_queue_contracts.py \
  tests/test_factory_runtime.py
```

Результат: `21 passed`.

```bash
python3 -m py_compile \
  ops/factory_lease_watchdog.py \
  ops/factory_control.py \
  ops/kolibri-dispatch \
  tests/test_factory_lease_watchdog.py
git diff --check
```

Результат: passed.

## Следующий шаг

Подключить Telegram summary для watchdog only-on-action: отправлять сообщение
только если `expired > 0`, `stuck > 0`, `requeued_* > 0`,
`dead_lettered_* > 0` или health != `ok`, чтобы не шуметь каждые 5 минут.
