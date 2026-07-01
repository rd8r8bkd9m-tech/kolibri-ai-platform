# Code Changes

Changed files:

- `ops/telegram_gateway.py`
- `ops/telegram_superfactory.py`
- `ops/telegram_webhook_migration.py`
- `tests/test_telegram_gateway.py`
- `tests/test_telegram_superfactory_contracts.py`
- `docs/telegram-superfactory.md`
- `docs/agent/runs/2026-07-01-p0-pr89-deletewebhook-safety-gate/01-summary.md`
- `docs/agent/runs/2026-07-01-p0-pr89-deletewebhook-safety-gate/02-code-changes.md`
- `docs/agent/runs/2026-07-01-p0-pr89-deletewebhook-safety-gate/03-verification.md`
- `docs/agent/runs/2026-07-01-p0-pr89-deletewebhook-safety-gate/04-risks-followups.md`
- `docs/agent/runs/2026-07-01-p0-pr89-deletewebhook-safety-gate/05-remote-result.md`

Implementation notes:

- Added `DELIVERY_STATE_MUTATION_METHODS` to the Telegram gateway client.
- `TelegramClient` now refuses `deleteWebhook`, `setWebhook`, `logOut`, and `close` unless a caller explicitly opts into delivery-state mutation.
- Added a separate owner-approved webhook migration module.
- Removed the ordinary startup path that used `TELEGRAM_ALLOW_WEBHOOK_DELETE` to delete webhooks before polling.
- Added tests that prove default startup does not call Telegram methods or open network connections when unsafe webhook environment variables are present.
