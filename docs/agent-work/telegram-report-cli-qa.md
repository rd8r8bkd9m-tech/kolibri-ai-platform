# Telegram-report CLI QA

Понятное название агента: Инженер Telegram-report CLI QA.
Дата: 2026-06-29.

## Scope

Изучен текущий `ops/telegram_gateway.py` после правок главного агента. Код не
менялся. Этот документ фиксирует, какие функции и CLI-контракты надо покрыть
тестами перед тем, как использовать `--send-report` как надежный канал
owner-facing отчетов.

Новая report-поверхность находится в `ops/telegram_gateway.py`:

- `sanitize_report_text()`;
- `split_telegram_text()`;
- `report_title_from_path()`;
- `build_report_letter()`;
- `state_owner_chat_id()`;
- `send_report_letter()`;
- `TelegramClient.send_text_document()`;
- `main()` с аргументами `--send-report`, `--report-chat-id`,
  `--report-title`, `--report-agent`, `--report-status`, `--report-summary`.

Существующие `tests/test_telegram_gateway.py` хорошо покрывают task/chat/image
сценарии, owner-safe formatting и часть redaction для обычных task results.
Отдельные тесты для report CLI, report sanitizer и разбиения длинного письма
сейчас нужны как следующий QA слой.

## Expected report behavior

`--send-report <path>` должен:

- требовать `TELEGRAM_BOT_TOKEN`, но не требовать `TELEGRAM_OWNER_IDS`;
- выбрать chat id из `--report-chat-id`, затем из
  `TELEGRAM_REPORT_CHAT_ID`, затем из state file `owner_chat_id`, затем из
  любого `tracked[*].chat_id`;
- при отсутствии chat id завершаться понятной ошибкой и не делать Telegram
  call;
- читать отчет как UTF-8, собирать письмо с темой, датой, ответственным,
  статусом, optional summary и sanitized body;
- отправлять длинный текст несколькими `sendMessage`-частями через
  `send_text_document()`;
- печатать в stdout JSON вида
  `{"event":"telegram_report_sent","chat_id":...,"parts":...,"title":"..."}`;
- не печатать token, секреты, private paths или raw report body в stdout/stderr.

## Unit tests to add

Рекомендуемые имена тестов можно держать в `tests/test_telegram_gateway.py` или
вынести в `tests/test_telegram_report_cli.py`.

| Test | Contract |
| --- | --- |
| `test_sanitize_report_text_redacts_secret_values_and_paths` | `token=...`, `secret=...`, `password=...`, `api_key=...`, `/var/lib/kolibri-agent/...`, `/run/secrets/...`, `/etc/kolibri/...`, `/tmp/...` заменяются безопасными маркерами. |
| `test_sanitize_report_text_hides_secret_lines` | Lines with `Authorization:`, `Cookie:`, `Set-Cookie:`, `private key`, `-----BEGIN` are replaced полностью. |
| `test_sanitize_report_text_handles_quoted_secret_values` | Обязательный edge-case: `token="fake"` and `token='fake'` must not leak. На текущем коде это QA gap: такие значения не редактируются. |
| `test_build_report_letter_sanitizes_body_and_summary` | Body and `summary` pass through sanitizer; headers are present; timestamp can be monkeypatched via `utc_now`. |
| `test_build_report_letter_title_agent_status_are_owner_safe` | Decide desired contract for `title`, `agent`, `status`. Сейчас они вставляются как-is, so tests should either ban secrets in caller inputs or drive a sanitizer patch later. |
| `test_report_title_from_path_humanizes_filename` | `foo-bar_baz.md` becomes `Foo bar baz`; empty/odd stems still return a non-empty title. |
| `test_state_owner_chat_id_prefers_owner_chat_id` | `owner_chat_id` wins over `tracked` fallback and is returned as `int`. |
| `test_state_owner_chat_id_falls_back_to_tracked_chat` | If no `owner_chat_id`, first tracked record with `chat_id` is used. |
| `test_state_owner_chat_id_missing_returns_none` | Empty state returns `None`; invalid values should be explicitly covered if the desired behavior is not to crash. |
| `test_send_report_letter_requires_chat_id_without_sending` | With no explicit/state/tracked chat id, raises the current RuntimeError and fake Telegram records zero sends. |
| `test_send_report_letter_explicit_chat_id_overrides_state` | `chat_id=` argument wins over saved state; result JSON contains selected chat id, title, parts. |
| `test_send_report_letter_uses_state_fallback` | No explicit chat id, saved `owner_chat_id` or tracked chat id sends successfully. |
| `test_split_telegram_text_empty_report` | Empty or whitespace-only report becomes `Пустой отчёт.`. |
| `test_split_telegram_text_keeps_chunks_under_limit` | Inputs at `limit`, `limit + 1`, long paragraph without spaces, and multiple paragraphs all produce non-empty chunks within limit. |
| `test_send_text_document_prefixes_multi_part_report` | Multi-part sends include `Title (i/n)` prefixes in order and return the number of parts. |
| `test_send_text_document_does_not_lose_body_with_long_title` | Required edge-case: a very long title prefix must not cause `send_message()` truncation to drop content. Current code can truncate at `3900`, so this may expose a follow-up fix. |
| `test_report_cli_send_report_prints_json_and_exits` | `main()` in send-report mode calls `send_report_letter()`, prints JSON, returns `0`, and does not instantiate `FactoryClient`/run polling. |
| `test_report_cli_send_report_does_not_require_owner_ids` | With token and report chat id set, no `TELEGRAM_OWNER_IDS` is needed. |
| `test_report_cli_daemon_mode_requires_owner_ids` | Without `--send-report`, missing `TELEGRAM_OWNER_IDS` still exits with the existing requirement. |
| `test_report_cli_env_defaults_and_arg_overrides` | `TELEGRAM_REPORT_*` env defaults are honored, CLI args override them, and invalid `TELEGRAM_REPORT_CHAT_ID` is handled deliberately. |

## Edge cases checklist

No `owner_chat_id`:

- empty state file;
- state file exists but has no `owner_chat_id`;
- state has only `tracked` records with one usable `chat_id`;
- explicit `--report-chat-id` provided;
- missing token plus missing chat id: CLI currently validates token first, so
  the missing-chat-id unit test should call `send_report_letter()` directly or
  provide a dummy token while monkeypatching Telegram network calls.

Secrets and private data:

- key/value markers: `token`, `secret`, `password`, `passwd`, `api_key`,
  `access_token`, `refresh_token`, `client_secret`;
- separators `=` and `:`;
- quoted values, because current sanitizer misses quoted fake values;
- whole-line secret markers: private key blocks, authorization headers, cookies;
- private runtime paths: `/var/lib/kolibri-agent`, `/run/secrets`,
  `/etc/kolibri`, `/tmp`;
- summary and body must be sanitized; title/agent/status need a decided policy;
- stdout/stderr from CLI must not include Telegram token, report body or
  exception text with the bot URL.

Long report and splitting:

- report below limit sends one message without prefix;
- report exactly at `REPORT_CHUNK_LIMIT` sends one message;
- report over limit sends multiple ordered parts;
- paragraphs split on blank lines where possible;
- single very long line splits without producing empty chunks;
- no chunk body exceeds `REPORT_CHUNK_LIMIT`;
- prefixed Telegram message should stay below the `send_message()` 3900-char
  slice to avoid silent truncation;
- Unicode Cyrillic text should not be corrupted by splitting;
- reconstructing sent chunks after removing prefixes should preserve the full
  sanitized letter.

## Verification commands

Current smoke for the existing file:

```bash
python3 -m py_compile ops/telegram_gateway.py
python3 -m pytest -q tests/test_telegram_gateway.py
```

After adding report tests:

```bash
python3 -m pytest -q tests/test_telegram_gateway.py -k 'report or split or owner_chat_id or send_text_document'
```

If tests are split into a dedicated file:

```bash
python3 -m pytest -q tests/test_telegram_report_cli.py
```

Production-only live smoke, after owner chat id and secret env are installed on
the control node:

```bash
set -a
. /etc/kolibri/telegram.env
set +a
python3 ops/telegram_gateway.py \
  --state-file /var/lib/kolibri-telegram-gateway/state.json \
  --send-report docs/agent-work/telegram-report-cli-qa.md \
  --report-title "Telegram report CLI QA" \
  --report-agent "Инженер Telegram-report CLI QA" \
  --report-status "qa-plan"
```

Do not run the live smoke in CI and do not paste real token values into command
history, reports or task envelopes.

## QA verdict

Report CLI is small and testable, but should not be treated as production-safe
until the report-specific tests above exist. Highest-risk gaps are quoted secret
redaction, header-field policy for title/agent/status, missing chat id behavior,
and lossless splitting for long reports with prefixes.
