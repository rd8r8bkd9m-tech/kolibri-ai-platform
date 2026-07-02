# Telegram Owner Relay Policy

Snapshot: 2026-07-02

## Law

Agents, KFM and MIMO Code may send owner-visible messages without knowing the
Telegram bot token. The token belongs to exactly one canonical Telegram gateway
and is referenced by capability, not copied to workers.

```text
capability: telegram_owner_notify
secret_ref: telegram_owner_bot_token
delivery_path: agent -> Control Plane -> Telegram gateway -> owner
```

## Why Raw Token Fan-Out Is Forbidden

- A bot token is a bearer credential.
- If every agent gets the raw token, there is no clean audit boundary.
- A leaked worker log would leak the bot.
- Rotating the token would require touching every agent.
- Telegram receiver ownership can split if workers start polling directly.

The correct factory shape is one receiver and many authorized notification
producers.

## Agent API

Agents send notifications through Control Plane:

```text
POST /v1/owner/notifications
```

Minimal body:

```json
{
  "source_node": "server-kfrm",
  "source_agent": "mimo-code",
  "task_id": "P0_EXAMPLE",
  "severity": "info",
  "title": "KFM update",
  "message": "Я закончил проверку и передал результат в артефакты.",
  "idempotency_key": "server-kfrm:P0_EXAMPLE:done"
}
```

Response contains a notification id and `secret_ref`, never the token.

## Gateway API

The canonical Telegram gateway polls and acknowledges notifications:

```text
GET /v1/owner/notifications?state=pending
POST /v1/owner/notifications/{notification_id}/ack
```

Only the gateway process reads `TELEGRAM_BOT_TOKEN` from its secret environment.

## Owner-Initiated Direct Messages

The owner can still write to the bot directly. The gateway converts owner
messages into Control Plane task envelopes. Agents answer through task artifacts
or owner notifications, not direct bot API calls.

## Secret Handling

- Do not commit the token.
- Do not put the token in task envelopes.
- Do not put the token in KFM memory.
- Do not print the token in logs.
- If the token was pasted into chat or logs, treat it as exposed and rotate it
  through the canonical secret install path.
- Agents may know `secret_ref=telegram_owner_bot_token`; they may not know its
  raw value.
