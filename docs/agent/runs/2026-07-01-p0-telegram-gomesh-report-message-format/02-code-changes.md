# Code Changes

Changed files:

- `ops/telegram_gateway.py`
- `tests/test_telegram_gateway.py`
- `docs/agent/runs/2026-07-01-p0-telegram-gomesh-report-message-format/01-summary.md`
- `docs/agent/runs/2026-07-01-p0-telegram-gomesh-report-message-format/02-code-changes.md`
- `docs/agent/runs/2026-07-01-p0-telegram-gomesh-report-message-format/03-verification.md`
- `docs/agent/runs/2026-07-01-p0-telegram-gomesh-report-message-format/04-risks-followups.md`
- `docs/agent/runs/2026-07-01-p0-telegram-gomesh-report-message-format/05-remote-result.md`

Implementation:

- Added GoMesh report-card detection before the generic completed owner-task formatter.
- Extracted stable fields from noisy agent report text: Home endpoint, health, Mbps metrics, target, selector, tests, rollback paths, and next action.
- Added token-like redaction for Telegram/API/GitHub/Slack-shaped secrets before parsing.
- Preserved only rollback backup paths as useful operational paths.
- Added a unit test using a noisy owner GoMesh report sample.
