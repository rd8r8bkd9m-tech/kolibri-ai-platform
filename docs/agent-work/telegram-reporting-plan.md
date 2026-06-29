# Telegram-reporting plan

Роль отчета: Инженер Telegram-отчетов.
Дата: 2026-06-29.

## Короткий вывод

Единственным процессом, который должен писать Владиславу в Telegram, остается
`kolibri-telegram-gateway.service`, запускающий `ops/telegram_gateway.py`.
Агенты и automations не должны напрямую использовать Telegram Bot API и не
должны получать `TELEGRAM_BOT_TOKEN`.

Текущий безопасный маршрут для отчетов:

1. Агент или automation работает через Control Plane task.
2. Статус, результат или ошибка фиксируются в Control Plane через task
   endpoints.
3. Telegram gateway опрашивает Control Plane, видит owner-visible задачи и
   отправляет Владиславу короткий очищенный статус.
4. Для audit trail агент также публикует событие в inter-agent feed через
   `/v1/agent-messages`.

Важно: текущий gateway не пересылает `/v1/agent-messages` напрямую в Telegram.
Feed - это общий журнал агентов. Telegram-доставка сейчас завязана на task
state/result.

## Изученные файлы

- `ops/telegram_gateway.py` - long-polling Telegram bot, owner authorization,
  task envelope creation, status formatting, redaction, transition polling.
- `ops/install-telegram-secret.sh` - удаленная установка `/etc/kolibri/telegram.env`
  с `TELEGRAM_BOT_TOKEN`.
- `ops/systemd/kolibri-telegram-gateway.service` - systemd unit gateway.
- `ops/systemd/kolibri-agent-host.env.example` - правила env для agent host и
  запрет хранить секреты в общем env example.
- `ops/systemd/kolibri-agent-host.service` и
  `ops/systemd/kolibri-factory-control.service` - runtime layout для Agent Host
  и Control Plane.
- `ops/factory_control.py` - `/v1/tasks`, `/v1/agent-messages`,
  idempotency key, retry budget, lease retry/dead-letter.
- `ops/agent_host.py` - task complete/fail, result artifacts, agent feed
  publishing, Telegram chat/image runners.
- `ops/kolibri-dispatch` - CLI path `submit --file`, `status`, `collect`,
  `cancel`.
- `tests/test_telegram_gateway.py` - contract tests for Telegram envelopes,
  owner-safe redaction, status formatting and image delivery.
- `docs/api.md`, `docs/factory.md`, `docs/deployment.md`,
  `ops/FACTORY_AUTONOMY.md`, `docs/project-policy.md`,
  `docs/desktop-control-app.md`, `docs/agent-work/factory-runtime-rollout.md`,
  `docs/agent-work/automation-control-plane-10-pack.md`,
  `docs/agent-work/docs-steward.md`.

## Как gateway сейчас работает

`ops/telegram_gateway.py` читает Telegram через `getUpdates` и разрешает вход
только private chat, где `message.from.id` входит в `TELEGRAM_OWNER_IDS`.
После первого сообщения Владислава gateway сохраняет `owner_chat_id` в state
file и может отправлять последующие owner-visible task updates в этот чат.

Для входящих сообщений gateway создает task envelopes:

- рабочая задача: `POST /v1/tasks`, `kind=owner_remote_task`,
  `required_capability=generic_implementation`,
  `idempotency_key=telegram:<chat_id>:<message_id>`;
- обычный разговор: `POST /v1/tasks`, `kind=owner_remote_task`,
  `runner=codex` по умолчанию,
  `idempotency_key=telegram-chat:<chat_id>:<message_id>`;
- генерация картинки: `POST /v1/tasks`, `kind=telegram_image_generation`,
  `idempotency_key=telegram-image:<chat_id>:<message_id>`.

Gateway дополнительно auto-tracks свежие owner-visible задачи:

- `envelope.kind == owner_remote_task`;
- или `envelope.source.kind` начинается с `telegram`;
- кроме `TGCHAT-*`;
- только если задача создана после `TELEGRAM_COMMON_CHAT_SINCE`.

При переходах `queued`, `leased`, `running`, `completed`, `failed`,
`cancelled`, `dead_letter` gateway формирует короткий текст для владельца.
Для `completed` owner task он смотрит `result.response`, вытаскивает безопасные
URL и скрывает внутренние детали.

## Что должны делать агенты и automations

### Если работа уже идет как Control Plane task

Агент должен завершать или фейлить исходную задачу через worker endpoints:

- `POST /v1/tasks/<task_id>/complete`;
- `POST /v1/tasks/<task_id>/fail`;
- `POST /v1/tasks/<task_id>/annotate` для безопасного дополнения результата.

`result.response` должен быть готовым owner-facing summary на русском:

```json
{
  "response": "Готово: коротко что изменилось.\nПроверки: pytest ... прошел.\nСледующий шаг: PR готов к проверке.",
  "pull_request_url": "https://github.com/...",
  "status": "completed"
}
```

В `response` нельзя вставлять raw logs, локальные пути, task/node/agent ids,
секреты, токены или env dumps. Технические доказательства лучше оставлять в
artifact manifest/result JSON, а в Telegram отправлять только короткий итог.

### Если automation хочет отдельный Telegram-отчет

На текущем коде не надо звать Telegram напрямую. Безопасный вариант:

1. Создать owner-visible Control Plane task через `ops/kolibri-dispatch submit
   --file <envelope.json>` или `POST /v1/tasks`.
2. Дать стабильный `task_id` и `idempotency_key`.
3. Положить в задачу короткую цель: подготовить owner-facing status report.
4. Завершить task обычным Agent Host путем или дождаться runner.

Минимальный envelope:

```json
{
  "task_id": "KOL-REPORT-<topic>-<yyyymmdd>",
  "idempotency_key": "telegram-report:<topic>:<yyyymmdd>",
  "kind": "owner_remote_task",
  "required_capability": "generic_implementation",
  "max_retries": 1,
  "objective": "Подготовь короткий безопасный отчет Владиславу: <тема>.",
  "source": {
    "kind": "automation",
    "automation": "<name>"
  }
}
```

Для audit trail параллельно можно публиковать:

```bash
curl -fsS -X POST "$KOLIBRI_FACTORY_CONTROL_URL/v1/agent-messages" \
  -H 'Content-Type: application/json' \
  -d '{"sender":"<node-or-automation>","recipients":["all"],"kind":"status","topic":"telegram-report","body":"Короткий sanitized статус","artifacts":[]}'
```

Но этот feed сам по себе не является Telegram-доставкой.

## Endpoint и скрипт

Основной способ для агентов и automations:

- `ops/kolibri-dispatch submit --file <envelope.json>`;
- напрямую: `POST /v1/tasks`;
- статус: `GET /v1/tasks?summary=1&compact=1&limit=200`;
- точечная проверка: `GET /v1/tasks/<task_id>`;
- результат: `ops/kolibri-dispatch collect <task_id>`;
- audit feed: `POST /v1/agent-messages`.

Gateway сам использует Telegram methods `sendMessage`, `editMessageText`,
`sendPhoto` через `TelegramClient`. Этот слой не должен становиться публичным
скриптом для всех агентов.

## Env на control node

Обязательные:

- `TELEGRAM_BOT_TOKEN` - секрет bot token. Хранить только в root-readable
  secret file/drop-in, не в repo и не в task envelope.
- `TELEGRAM_OWNER_IDS` - Telegram user id Владислава, можно несколько через
  comma/semicolon. Это user id, а не произвольный chat title.
- `KOLIBRI_FACTORY_CONTROL_URL` - основной Control Plane URL.

Рекомендуемые:

- `KOLIBRI_FACTORY_CONTROL_URLS` - comma-separated failover list.
- `TELEGRAM_GATEWAY_STATE` - state file, по unit сейчас
  `/var/lib/kolibri-telegram-gateway/state.json`.
- `TELEGRAM_POLL_TIMEOUT` - long polling timeout, default `25`.
- `TELEGRAM_COMMON_CHAT_SINCE` - нижняя граница auto-tracking свежих
  owner-visible задач.

Опциональные task routing knobs:

- `TELEGRAM_TASK_KIND`, default `owner_remote_task`;
- `TELEGRAM_TASK_CAPABILITY`, default `generic_implementation`;
- `TELEGRAM_TASK_MAX_RETRIES`, default `1`;
- `TELEGRAM_TASK_NODE`;
- `TELEGRAM_OWNER_PROJECT_PATH`;
- `TELEGRAM_CHAT_KIND`, default `owner_remote_task`;
- `TELEGRAM_CHAT_CAPABILITY`, default `generic_implementation`;
- `TELEGRAM_CHAT_RUNNER`, default `codex`;
- `TELEGRAM_CHAT_NODE`, default `primary-candidate`;
- `TELEGRAM_CHAT_WAIT_SECONDS`, default `90`;
- `TELEGRAM_CHAT_FIRST_REPLY_SECONDS`, default `0`;
- `TELEGRAM_IMAGE_KIND`, default `telegram_image_generation`;
- `TELEGRAM_IMAGE_CAPABILITY`, default `generic_implementation`;
- `TELEGRAM_IMAGE_MAX_RETRIES`, default `1`;
- `TELEGRAM_IMAGE_RUNNER`, default `image`;
- `TELEGRAM_IMAGE_NODE`;
- `TELEGRAM_DETERMINISTIC_SHORTCUTS`.

Agent Host side:

- `KOLIBRI_FACTORY_CONTROL_URL` и `KOLIBRI_FACTORY_CONTROL_URLS` должны
  совпадать с control node.
- Нода, которая отвечает на Telegram chat/task, должна иметь capability
  `generic_implementation`.
- Для image tasks нужен runner image path: `KOLIBRI_IMAGE_GENERATOR_CMD` или
  `OPENAI_API_KEY` через секретный канал. `OPENAI_API_KEY` нельзя класть в
  `ops/systemd/kolibri-agent-host.env.example`.
- Для Codex/Mimo runners auth хранится в secret manager или отдельном
  root-readable файле, не в envelope и не в owner report.

## Что нельзя отправлять Владиславу в Telegram

Нельзя отправлять:

- значения `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `CODEX_ACCESS_TOKEN`,
  T-Банк credentials, GitHub tokens, SSH keys, cookies, OAuth/cache files;
- `.env`, `auth.json`, private key files, shell history и полные env dumps;
- raw `stdout.log`, `stderr.log`, traceback, command transcript с env;
- приватные customer docs, investor contacts, персональные данные без явного
  разрешения;
- node-local пути вроде `/var/lib/kolibri-agent/...`, worktree paths,
  artifact paths, result paths и log paths;
- внутренние `task_id`, `node_id`, `agent_id`, lease owner, pid, hostname,
  SSH alias без явной debug-просьбы;
- большие payloads из `/v1/tasks` и raw result JSON;
- IP/URL внутреннего контура, если это не owner-approved preview/public URL.

Разрешенный формат:

- 1-5 коротких строк;
- что сделано;
- какие проверки прошли;
- где смотреть owner-safe результат: public preview, PR URL, issue URL;
- блокер и следующий безопасный шаг, если работа не готова.

## Redaction contract

В `ops/telegram_gateway.py` уже есть `clean_agent_response()` и forbidden
markers для `task_id`, `node:`, `agent:`, `artifact:`, `worktree`,
`result_path`, `log_path`, `/var/lib`, `/tmp/`, `secret`, `token`, `_key`,
`env_file`, `TGCHAT-*`, `TG-202*`. Тесты покрывают скрытие node/agent/path и
сценарий, где response упоминает `TELEGRAM_BOT_TOKEN`.

Агентам не нужно полагаться только на gateway redaction. Секреты не должны
попадать в `result.response` вообще. Redaction - последняя страховка, а не
нормальный путь публикации.

## Retry и idempotency

Для любой задачи-отчета нужен стабильный `idempotency_key`. Рекомендованный
формат:

```text
telegram-report:<automation-or-agent>:<topic-or-input-hash>:<date-or-version>
```

Правила:

- повторная отправка того же logical report должна использовать тот же
  `idempotency_key`;
- не включать в `idempotency_key` секреты, raw owner text, токены или длинные
  приватные payloads;
- при transient failure не создавать duplicate task вручную - Control Plane
  вернет существующую задачу по idempotency key;
- `max_retries=1` достаточно для owner notifications и chat/image задач;
- `max_retries=2` допустим для инфраструктурной работы, где повтор может
  реально помочь;
- если lease истек, Control Plane сам переводит задачу через
  `retry_scheduled` обратно в queue до исчерпания retry budget;
- если retry budget исчерпан, задача становится `failed` или `dead_letter`, а
  Telegram должен получить короткий blocker summary без raw logs;
- ручной `/retry <task_id>` в Telegram создает новую задачу с новым
  `retry:<old>:<timestamp>` idempotency key. Использовать только как явное
  operator action.

Telegram delivery itself is at-least-once. Gateway обновляет tracked
`last_state` после успешной отправки. Если Telegram принял сообщение, но state
save упал, возможен повтор. Поэтому owner-facing отчеты должны быть
идемпотентны по смыслу: повтор одного и того же статуса не должен запускать
новые действия.

## Минимальные безопасные патчи, которые стоит сделать позже

Код в рамках этого отчета не менялся. Маленькие патчи-кандидаты:

1. `ops/systemd/kolibri-telegram-gateway.env.example`
   - добавить пример env без значений секретов;
   - явно показать `TELEGRAM_OWNER_IDS`, `KOLIBRI_FACTORY_CONTROL_URLS`,
     `TELEGRAM_GATEWAY_STATE`, retry/routing knobs;
   - отметить, что token values не коммитятся.

2. `ops/install-telegram-secret.sh`
   - дополнительно спрашивать `TELEGRAM_OWNER_IDS`;
   - писать token и owner ids в `/etc/kolibri/telegram.env` с `0600`;
   - не печатать введенные значения;
   - не затирать неуправляемые non-secret строки без необходимости.

3. `ops/systemd/kolibri-telegram-gateway.service`
   - добавить `StateDirectory=kolibri-telegram-gateway` или отдельную установку
     state dir, чтобы user `kolibri` мог создать/write state file под
     `/var/lib/kolibri-telegram-gateway`.

4. `ops/telegram_gateway.py` и `tests/test_telegram_gateway.py`
   - расширить forbidden markers для `password`, `cookie`, `authorization`,
     `private_key`, `.env`, `stdout.log`, `stderr.log`;
   - добавить тест, что такие строки вырезаются из owner-facing response.

5. Отдельный behavior patch, если нужен прямой мост feed -> Telegram:
   - `ops/telegram_gateway.py`: добавить чтение
     `/v1/agent-messages?target=owner&limit=...`, хранить последний
     `message_id` в state, отправлять только `kind=owner_report` после
     `clean_agent_response`;
   - `ops/factory_control.py`: контракт для `recipients=["owner"]`;
   - `tests/test_telegram_gateway.py`: idempotent delivery, redaction,
     duplicate suppression;
   - `docs/api.md`: описать `owner_report`.

Пятый пункт уже меняет поведение, поэтому его лучше делать отдельной задачей с
тестами, а не как скрытую правку в документационном отчете.

## Rollout checklist

- Владислав написал боту хотя бы одно private сообщение, gateway сохранил
  `owner_chat_id`.
- `/etc/kolibri/telegram.env` содержит `TELEGRAM_BOT_TOKEN` и
  `TELEGRAM_OWNER_IDS`, права `0600`.
- `systemctl status kolibri-telegram-gateway` без restart loop.
- Gateway state dir существует и writable для service user.
- `curl "$KOLIBRI_FACTORY_CONTROL_URL/health"` возвращает `status=ok`.
- `curl "$KOLIBRI_FACTORY_CONTROL_URL/v1/nodes"` показывает хотя бы одну
  online ноду с `generic_implementation`.
- Test task с `kind=owner_remote_task`, стабильным `idempotency_key` и
  `max_retries=1` попадает в queue.
- При `completed` Telegram получает только короткий sanitized итог.
- При `failed/dead_letter` Telegram получает blocker summary без raw logs.
- Повторный submit с тем же `idempotency_key` не создает duplicate task.
- `/v1/agent-messages` получает audit event, но owner-facing секреты туда тоже
  не попадают.

## Локальные проверки для этого отчета

Рекомендуемый минимум после правок gateway/systemd:

```bash
python3 -m py_compile ops/telegram_gateway.py ops/factory_control.py ops/agent_host.py
python3 -m pytest -q tests/test_telegram_gateway.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py
```

Для production node дополнительно:

```bash
systemctl status kolibri-telegram-gateway --no-pager
journalctl -u kolibri-telegram-gateway -n 100 --no-pager
curl -fsS "$KOLIBRI_FACTORY_CONTROL_URL/health"
curl -fsS "$KOLIBRI_FACTORY_CONTROL_URL/v1/tasks?summary=1&compact=1&limit=50"
```

Перед публикацией любых логов из `journalctl` их нужно просмотреть на секреты и
приватные пути.
