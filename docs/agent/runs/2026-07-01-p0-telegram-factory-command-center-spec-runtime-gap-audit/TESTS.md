# Tests

Task: `P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01`

## Remote Evidence

Control Plane result:

- state: `failed`
- error:
  `command failed with rc=1: test -f docs/product/telegram-command-center/2026-07-01/COMMAND_CENTER_SPEC.md`

Useful remote checks reported:

- exactly two docs were created in non-contract docs paths.
- exactly five remote artifact files were created.
- no product code, tests, backend/frontend implementation, runtime services,
  GitHub Actions, or live Telegram operations were reported.

## Local Relay Checks

Run after relay:

```bash
git diff --check
test -f docs/product/telegram-command-center/2026-07-01/COMMAND_CENTER_SPEC.md
test -f docs/product/telegram-command-center/2026-07-01/TELEGRAM_RUNTIME_GAP_AUDIT.md
test -f docs/product/telegram-command-center/2026-07-01/BOT_RUNTIME_CONTRACT.md
test -f docs/product/telegram-command-center/2026-07-01/MINI_APP_UX_SPEC.md
test -f docs/product/telegram-command-center/2026-07-01/OWNER_AUTH_AND_INITDATA_POLICY.md
test -f docs/product/telegram-command-center/2026-07-01/RICH_STREAMING_REPORTS_PLAN.md
test -f docs/product/telegram-command-center/2026-07-01/BUSINESS_GUEST_BOT_SAFETY_POLICY.md
test -f docs/product/telegram-command-center/2026-07-01/IMPLEMENTATION_SLICES.md
test -f docs/product/telegram-command-center/2026-07-01/NEXT_TASK_PROMPTS.md
```
