# Next

Exact next task:

`P0_TELEGRAM_FACTORY_BOT_MENU_CONTRACT_2026_07_02`

Goal:

Add a repository-only advertised command menu contract for the Telegram factory bot. The owner-facing command menu target is exactly `/start`, `/status`, `/help`. Keep any legacy operational slash commands owner-only and unadvertised unless a later owner-approved runtime menu migration changes that.

Read first:

- `docs/product/telegram-command-center/2026-07-02/TELEGRAM_FACTORY_BOT_GATE_ANALYSIS.md`
- `ops/telegram_gateway.py`
- `ops/telegram_superfactory.py`
- `tests/test_telegram_gateway.py`

Acceptance:

- A small command contract helper exists in code or tests.
- Tests prove the advertised menu contains only `/start`, `/status`, `/help`.
- Tests prove no ordinary startup/test path calls `setMyCommands`.
- No live Telegram Bot API mutation.
- No token printing.
- No service restart.
