# Factory lease watchdog Telegram-on-action

Дата: 2026-06-29
Ветка: `codex/factory-autonomy-pwa-billing`

## Цель

Lease watchdog уже каждые 5 минут запускает `reap-expired` и `sweep-stuck`.
Эта правка добавляет owner notification без шума: Telegram-отчет отправляется
только если watchdog реально что-то исправил или увидел проблему.

## Добавлено

- `should_notify(summary)`:
  - отправлять, если health status не `ok`;
  - отправлять, если `expired`, `stuck`, `requeued_*` или `dead_lettered_*`
    больше нуля;
  - не отправлять "все спокойно" каждые 5 минут.
- Встроенный минимальный Telegram sender в `ops/factory_lease_watchdog.py`.
- Чтение owner chat id из `TELEGRAM_REPORT_CHAT_ID` или
  `/var/lib/kolibri-telegram-gateway/state.json`.
- Sanitizer для token/secret/password/api key строк.
- Systemd unit теперь подключает optional `/etc/kolibri/telegram.env` и
  запускает watchdog с `--telegram-on-action`.

## Live deploy evidence

Main server: `root@10.99.0.2`

Service:

```text
ExecStart=/usr/local/bin/kolibri-factory-lease-watchdog --telegram-on-action
code=exited, status=0/SUCCESS
```

Timer:

```text
kolibri-factory-lease-watchdog.timer: active
```

Latest live report:

```json
{
  "summary": {
    "status": "ok",
    "redis": "PONG",
    "task_total": 693,
    "lease_index_total": 1,
    "expired": 0,
    "stuck": 0,
    "requeued_expired": 0,
    "requeued_stuck": 0,
    "dead_lettered_expired": 0,
    "dead_lettered_stuck": 0,
    "stale_after_seconds": 3600
  },
  "telegram": {
    "status": "skipped",
    "reason": "no_action"
  }
}
```

Это правильное поведение: watchdog жив, но не спамит владельцу, пока нет
исправленных или проблемных задач.

## Локальные проверки

```bash
/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_lease_watchdog.py
```

Результат: `7 passed`.

```bash
python3 -m py_compile ops/factory_lease_watchdog.py tests/test_factory_lease_watchdog.py
git diff --check
```

Результат: passed.

## Следующий шаг

Добавить aggregated daily/shift summary для владельца: сколько задач watchdog
вернул в очередь, сколько отправил в dead-letter и какие node/agent owners чаще
всего зависают.
