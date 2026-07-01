# P0 Telegram Main Receiver Token Lineage Identity Result

Task: `P0_TELEGRAM_MAIN_RECEIVER_TOKEN_LINEAGE_AND_IDENTITY_2026_07_01`

## Outcome

Control Plane task failed because the `main` Codex runner auth is broken, but a
remote read-only SSH diagnostic fallback completed the identity check.

## Confirmed Facts

Active receiver:

- Node: `main`
- Hostname: `kolibri-main-api`
- Service: `kolibri-telegram-gateway.service`
- State: `active/running`
- Main PID present.
- State file exists and has a present Telegram update offset.

Bot identity:

- `getMe` succeeded.
- Bot username: `kolibriai_bot`.
- Username matches expected `@kolibriai_bot`: `true`.

Delivery mode:

- `getWebhookInfo` succeeded.
- Webhook URL is empty.
- Pending updates: `0`.
- Allowed updates: `message`.

Safety:

- No update-consuming API call was made.
- No webhook mutation was made.
- No token value, token hash, owner chat ID or private message was printed.
- No service mutation was made.
- No product code was modified.

## Interpretation

The active live Telegram receiver for `@kolibriai_bot` is currently the
long-polling `kolibri-telegram-gateway.service` on `main`.

PR #89 must remain draft until a controlled cutover plan reconciles the current
live `main` receiver with the PR #89 Telegram Superfactory implementation.

## Remaining Risk

The `main` Codex runner is not usable until re-authenticated or replaced with a
runner that can execute without expired ChatGPT/Codex credentials.
