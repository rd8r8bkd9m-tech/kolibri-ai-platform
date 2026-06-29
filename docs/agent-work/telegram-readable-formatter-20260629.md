# KOL-TELEGRAM-FORMAT-001 — отчет

Дата: 2026-06-29
Ответственный: Codex
Статус: deployed

## Что исправлено

- Добавлен единый модуль форматирования `formatTelegramMessage(event)` в `ops/telegram_gateway.py`.
- `TelegramClient.send_message` теперь отправляет сообщения через Telegram `sendMessage` с `parse_mode=HTML`.
- HTML экранируется для символов `&`, `<`, `>`, `"`, `'`, `’`.
- Сообщения длиннее 4096 символов разбиваются на части перед отправкой.
- Событийные payload больше не уходят владельцу как raw JSON: словари форматируются в человекочитаемые шаблоны.
- Raw JSON остается техническим артефактом в логах/результатах, а владелец получает короткое HTML-сообщение и ссылку на отчет/артефакт, если она есть в событии.

## Шаблоны

Покрыты шаблоны:

- `TASK_STARTED`
- `TASK_PROGRESS`
- `TASK_DONE`
- `TASK_FAILED`
- `BLOCKER`
- `FACTORY_STATUS`
- `PR_CREATED`
- `CI_RESULT`

## Before

```json
{"type":"TASK_FAILED","task_id":"KOL-RAW","reason":{"error":"<boom>","raw":true}}
```

## After

```html
<b>❌ Колибри: задача упала</b>
Task: KOL-RAW
Статус: FAILED
Причина: {&#39;error&#39;: &#39;&lt;boom&gt;&#39;, &#39;raw&#39;: True}
Следующий шаг: перезапускаю или передаю на разбор
```

## Проверки

- `python3 -m py_compile ops/telegram_gateway.py tests/test_telegram_gateway.py`
- `/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_telegram_gateway.py`
- `/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_telegram_gateway.py tests/test_factory_lease_watchdog.py tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py tests/test_agent_host_telegram_chat.py`
- `git diff --check`

Результат расширенного набора: `63 passed`.

## Деплой

- Файл развернут на control node: `/usr/local/bin/kolibri-telegram-gateway`
- Сервис перезапущен: `kolibri-telegram-gateway.service`
- Статус после перезапуска: `active (running)`

## Риски

- Для максимально чистых причин ошибок в шаблонах следующие итерации могут добавить компактную нормализацию вложенных dict/list в одну строку без Python-представления. Баг raw JSON в Telegram закрыт текущим патчем.
