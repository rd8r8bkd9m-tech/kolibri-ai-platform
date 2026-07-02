# Actions

- Confirmed the checkout was clean and on `agent/P0_EXEC_TELEGRAM_FACTORY_BOT_MENU_AND_AI_2026_07_02/generic`, not `main`.
- Updated `ops/telegram_gateway.py` so default Telegram API calls block bot profile/menu mutations:
  - `setMyCommands`
  - `deleteMyCommands`
  - `setChatMenuButton`
- Added `FactoryClient.get_artifacts(task_id)` and `/artifacts <task_id>` handling through the existing `/v1/agents/artifacts/{task_id}` control-plane route.
- Added owner-facing artifact formatting that filters local runtime roots, token-looking strings, and secret/password-like artifact labels before sending Telegram text.
- Kept dispatch/status/retry/cancel command behavior intact and preserved Russian human reply style for owner messages.
- Updated the Mini App static shell copy to present task/status/artifact control instead of an extra command menu.
- Added focused tests for menu mutation blocking and sanitized artifact command output.
- Committed and pushed `origin/agent/P0_EXEC_TELEGRAM_FACTORY_BOT_MENU_AND_AI_2026_07_02/generic`.
- Attempted direct PR creation, but `gh` is not installed in this environment. GitHub returned the browser PR creation URL in `RESULT.md`.
