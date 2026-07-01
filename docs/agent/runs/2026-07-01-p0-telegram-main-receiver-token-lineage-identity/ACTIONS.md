# P0 Telegram Main Receiver Token Lineage Identity Actions

Remote node:
- `main`
- SSH alias used by dispatcher: `kolibri-main`
- Hostname: `kolibri-main-api`

Control Plane attempt:

- Task accepted and leased to `main:agent-host-main`.
- Task failed before probe because `/usr/bin/codex exec` returned auth errors:
  `token_expired` / refresh token already used.
- No useful task artifacts were produced by the Codex runner.

SSH diagnostic fallback:

- Read service metadata for `kolibri-telegram-gateway.service`.
- Read `/var/lib/kolibri-telegram-gateway/state.json` metadata only.
- Parsed `/etc/kolibri/telegram.env` in memory to access the bot token without
  printing token values or hashes.
- Called Telegram Bot API `getMe`.
- Called Telegram Bot API `getWebhookInfo`.

Not done:

- No `getUpdates`.
- No `setWebhook`.
- No `deleteWebhook`.
- No token rotation.
- No service stop/restart.
- No product code modification.
