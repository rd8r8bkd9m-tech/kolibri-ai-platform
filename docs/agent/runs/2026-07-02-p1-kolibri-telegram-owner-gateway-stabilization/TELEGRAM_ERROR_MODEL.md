# Telegram Error Model

Task id: P1_KOLIBRI_TELEGRAM_OWNER_GATEWAY_STABILIZATION_2026_07_02
Date: 2026-07-02
Scope: owner-safe error handling for the Telegram gateway.

## Principles

- Telegram is an owner interface, not a log stream.
- Every owner-visible error is human Russian text.
- Technical evidence stays in run artifacts, tests, Control Plane state, or server logs after redaction.
- No error path may reveal secrets, paths, internal IDs, raw prompts, stack traces, HTTP bodies, or command lines.

## Error Classes

| Class | Example source | Owner message behavior | Internal handling |
| --- | --- | --- | --- |
| Unauthorized chat | Non-owner private chat or non-private chat | `Доступ запрещен.` | Do not route to Control Plane |
| Control Plane unavailable on task submit | `create_task` exception | Say the task/message was heard but not queued; investigation is separate | Record failed work memory where implemented |
| Control Plane unavailable on chat submit | `create_task` exception | Say chat task was not accepted and reply will resume after recovery | Do not leak exception text |
| Runner failure | Failed/dead-letter chat task | Say executor failed and technical noise is withheld | Remove tracked task when terminal |
| Status read failure | `get_task`/`get_tasks`/`nodes` exception | Prefer redacted unavailable summary in future hardening | Current residual gap for some command reads |
| Telegram send failure | Bot API send/edit/photo error | Do not retry with unsafe content | Keep live mutation outside tests |
| Image delivery failure | Missing/invalid image deliverable | Send safe failure summary through transition handling | Do not expose path or MIME internals |
| Payload redaction risk | Result contains paths/tokens/stderr | Strip or replace unsafe content | Add regression fixture before behavior expansion |

## Required Owner Fallbacks

Task submit failure:

```text
Я услышал задачу, но Control Plane сейчас не принял её в очередь. Зафиксировал сбой и разбираю отдельно.
```

Chat submit failure:

```text
Я услышал сообщение, но Control Plane сейчас не принял чат-задачу. Зафиксировал сбой и отвечу после восстановления контура.
```

Image submit failure:

```text
Я понял запрос на изображение, но фабрика сейчас не приняла задачу. Зафиксировал сбой и разберу отдельно.
```

Runner failure:

```text
Внутри фабрики упал исполнитель. Я не буду выносить технический мусор в чат: зафиксировал сбой и переключаю разбор на рабочий контур.
```

## Forbidden Error Content

- Python exception class names when they identify implementation internals.
- HTTP method, URL, response body, or Redis/backend endpoint details.
- `task_id`, raw node/agent IDs, branch names, paths, PIDs, leases, artifact IDs, and trace IDs.
- Tokens, API keys, env var values, credentials, webhook URLs, bot token lineage, or poller offsets.
- Runner prompts, owner raw prompt bundles, chain-of-thought style content, command invocations, or stderr.

## Validation

Current covered cases:

- Control Plane task submit failure is redacted.
- Control Plane chat submit failure is redacted.
- Runner prompt/tool-output failure is redacted by Agent Host chat tests.
- `/nodes`, `/agents`, and `/queue` summary output is redacted.

Recommended next tests:

- Read-path failures for `/status`, `/cancel`, `/retry`, `/nodes`, `/agents`, and `/queue`.
- Nested result payload redaction for completed and failed tasks.
- Telegram send/edit failure behavior with fake client exceptions.

