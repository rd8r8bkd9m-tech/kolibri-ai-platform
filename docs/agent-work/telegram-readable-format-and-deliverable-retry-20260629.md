# Telegram readable format and deliverable retry

Дата: 2026-06-29
Ответственный: Codex / Kolibri factory control
Статус: выполнено и задеплоено

## Что исправлено

- Telegram gateway больше не отправляет владельцу raw JSON для status events.
- Добавлен human-readable formatter `formatTelegramMessage(event)` с HTML escaping.
- `sendMessage` использует `parse_mode=HTML`.
- Длинные Telegram-сообщения делятся на части до лимита Telegram.
- Nested dict/list значения форматируются в читаемые строки, а не как Python/JSON-словарь.
- Markdown-отчёты перед отправкой в Telegram вырезают fenced `json` блоки; полный JSON остаётся в файлах отчёта.
- Watchdog Telegram-отчёты тоже переведены на HTML escaping и `parse_mode=HTML`.
- Watchdog теперь создаёт конкретную retry-задачу для новых `deliverable_gate_failed`, а не только наблюдает.

## Изменённые файлы

- `ops/telegram_gateway.py`
- `ops/factory_lease_watchdog.py`
- `tests/test_telegram_gateway.py`
- `tests/test_factory_lease_watchdog.py`

## Тесты

- `python3 -m py_compile ops/telegram_gateway.py ops/factory_lease_watchdog.py`
- `/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_telegram_gateway.py tests/test_factory_lease_watchdog.py`
  - Результат: 55 passed.
- `/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_telegram_gateway.py tests/test_factory_lease_watchdog.py tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_runtime.py tests/test_factory_autonomy_contracts.py`
  - Результат: 97 passed.
- `git diff --check`
  - Результат: passed.

## Деплой

Сервер: `10.99.0.2`

- `/usr/local/bin/kolibri-telegram-gateway` обновлён.
- `/usr/local/bin/kolibri-factory-lease-watchdog` обновлён.
- `kolibri-telegram-gateway.service`: active.
- `kolibri-factory-lease-watchdog.timer`: active.

## Live smoke

Telegram gateway smoke:

- Отправлен отчёт `Kolibri Telegram formatter smoke`.
- Результат: `telegram_report_sent`, `parts=1`.
- В отчёте был raw JSON block, но в Telegram он не отправляется.

Deliverable retry smoke:

- Создана контролируемая задача: `KOL-TELEGRAM-FORMAT-SMOKE-20260629084445`.
- Завершение без evidence ожидаемо вернуло `422 deliverable_gate_failed`.
- Watchdog создал retry-задачу:
  - `KOL-TELEGRAM-FORMAT-SMOKE-20260629084445-DELIVERABLE-RETRY`
  - `state=queued`
  - `kind=generic_implementation`
  - `idempotency_key=deliverable-retry:KOL-TELEGRAM-FORMAT-SMOKE-20260629084445`
- Watchdog отправил Telegram-отчёт `Kolibri watchdog: deliverable retry`, `parts=1`.

## До

```text
{"type":"TASK_FAILED","task_id":"KOL-RAW","reason":{"error":"<boom>","raw":true}}
```

## После

```text
❌ Колибри: задача упала
Task: KOL-RAW
Статус: FAILED
Причина: error: &lt;boom&gt;; raw: да
Следующий шаг: перезапускаю или передаю на разбор
```

## Источник API

- Telegram Bot API `sendMessage`: https://core.telegram.org/bots/api#sendmessage
- Telegram Bot API formatting options: https://core.telegram.org/bots/api#formatting-options

