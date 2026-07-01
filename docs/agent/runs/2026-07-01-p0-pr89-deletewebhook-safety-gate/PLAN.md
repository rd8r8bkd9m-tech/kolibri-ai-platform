# P0 PR89 DeleteWebhook Safety Gate

Task ID: `P0_PR89_DELETEWEBHOOK_SAFETY_GATE_2026_07_01`

Objective: ensure ordinary Telegram gateway startup cannot delete webhooks, set webhooks, rotate delivery state, drop pending updates, or start any receiver other than the existing main long-polling gateway.

Outcome:

- Default `ops/telegram_gateway.py` startup uses a guarded `TelegramClient`.
- Telegram delivery-state mutation methods are denied by default.
- Webhook deletion lives only in `ops/telegram_webhook_migration.py`.
- The systemd service still starts only `kolibri-telegram-gateway`.
- No live Telegram APIs or services were called during this run.
