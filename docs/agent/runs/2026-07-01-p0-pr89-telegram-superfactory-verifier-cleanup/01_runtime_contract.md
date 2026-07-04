# Runtime Contract

Task: `P0_PR89_TELEGRAM_SUPERFACTORY_VERIFIER_CLEANUP_2026_07_01`

This run preserves the Telegram Superfactory runtime contract from PR #89 and
adds only verifier/artifact cleanup.

- Canonical update receiver: `kolibri-telegram-gateway`.
- Supported receiver modes: `polling`, `webhook`, `disabled`.
- Polling conflict rule: refuse polling when Telegram already has a webhook,
  unless an operator explicitly sets `TELEGRAM_ALLOW_WEBHOOK_DELETE=1` for a
  one-time migration restart.
- Secrets policy: tokens, owner identifiers, cookies, API keys, passwords,
  private messages and raw logs are not printed.

No token rotation, pending update deletion, or second poller enablement was
performed during this cleanup.
