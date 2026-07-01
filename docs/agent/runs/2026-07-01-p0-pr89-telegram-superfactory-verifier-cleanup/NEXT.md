# Next

Recommended next task:

`P0_TELEGRAM_SINGLE_CANONICAL_RECEIVER_MIGRATION_2026_07_01`

Goal:

Prove and enforce that `@kolibriai_bot` has exactly one live update receiver
before enabling the new Telegram Superfactory runtime.

Acceptance:

- Identify the current active Telegram update receiver.
- Confirm whether the final mode is webhook or polling.
- Stop stale receivers only after evidence is captured.
- Do not delete pending updates unless explicitly approved.
- Do not rotate the Telegram token unless explicitly approved.
- Keep `kolibri-telegram-gateway` as the canonical receiver.
- Verify owner-visible commands remain `/start`, `/status`, and `/help`.
- Verify the menu button remains `Пульт фабрики` pointing to
  `https://kolibriai.ru/?telegram=1`.

PR #89 should remain draft until the single-receiver migration plan is reviewed
and the owner approves live deployment.
