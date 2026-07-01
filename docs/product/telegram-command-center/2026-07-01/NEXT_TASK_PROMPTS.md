# Next Task Prompts

Task: `P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01`

## Next Remote Task

Task id:

`P0_TELEGRAM_MINIAPP_OWNER_AUTH_CONTRACT_2026_07_01`

Goal:

Implement the backend Telegram Mini App owner-auth contract on a server branch.
Add `initData` verification, short-lived session issuance, role mapping,
redaction tests, and fixed signed fixtures. Do not implement the Mini App UI,
task mutation APIs, Telegram live receiver changes, webhook changes, service
restart, payments, Guest Mode, Business mode, or Bot-to-Bot behavior.

Read first:

- `docs/product/telegram-command-center/2026-07-01/COMMAND_CENTER_SPEC.md`
- `docs/product/telegram-command-center/2026-07-01/OWNER_AUTH_AND_INITDATA_POLICY.md`
- `backend/main.py`
- `ops/telegram_gateway.py`
- `tests/test_telegram_gateway.py`

Required output:

- server branch
- focused tests
- exact `PLAN.md`, `ACTIONS.md`, `TESTS.md`, `RESULT.md`, `NEXT.md`
- PR-sized change only
- no live Telegram mutation

## Later Tasks

- Read-only command center APIs.
- Mini App read-only shell.
- Command composer and task submit.
- Safe task actions.
- PR/CI/artifact views.
- Rich report renderer.
- Streaming.
