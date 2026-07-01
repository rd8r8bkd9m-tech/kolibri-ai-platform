# Next

Task: `P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01`

## Next Recommended Remote Task

`P0_TELEGRAM_MINIAPP_OWNER_AUTH_CONTRACT_2026_07_01`

Implement only the backend owner-auth contract for Telegram Mini App:

- `initData` verification
- short-lived session
- role mapping
- redaction
- fixed signed fixtures/tests

Do not include:

- Mini App UI
- task mutation
- live Telegram receiver changes
- webhook changes
- service restarts
- payments
- Guest Mode
- Bot-to-Bot
- Business mode

## Dispatcher Follow-Up

Create a new envelope only after this relay is committed and the owner-visible
task ledger records the failed verifier plus useful imported docs.
