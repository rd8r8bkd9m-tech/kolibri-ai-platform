# Smoke Checks

Task: `P0_TELEGRAM_PR89_MAIN_RECEIVER_CUTOVER_PLAN_2026_07_01`

These checks are designed to avoid Telegram API state changes during preflight
and to prove the rollout preserves one receiver.

## Local Repository Verification

Run from the repository checkout:

```bash
git diff --check
python3 -m py_compile ops/telegram_gateway.py ops/factory_control.py ops/agent_host.py
python3 -m pytest tests/test_telegram_gateway.py tests/test_agent_host_telegram_chat.py
python3 -m pytest tests/test_telegram_superfactory_contracts.py tests/test_telegram_superfactory_miniapp.py tests/test_factory_control_superfactory.py
```

Expected:

- Existing gateway tests pass.
- PR #89 Superfactory contract tests pass.
- No syntax errors.
- No whitespace errors.

## Receiver Static Checks

Run without calling Telegram:

```bash
git grep -n 'getUpdates\|deleteWebhook\|setWebhook' -- ops tests docs
git diff --name-status origin/main...origin/pr/89
```

Expected:

- Only `kolibri-telegram-gateway` owns `getUpdates`.
- `setWebhook` is absent from runtime code.
- `deleteWebhook` is present only in the explicit PR #89 migration path and is
  not reachable in the approved standard cutover.

## Live Pre-Restart Smoke

Read-only commands only:

```bash
systemctl is-active kolibri-telegram-gateway.service
pgrep -af 'kolibri-telegram-gateway|ops/telegram_gateway.py'
journalctl -u kolibri-telegram-gateway.service -n 80 --no-pager
```

Expected:

- One active service.
- One matching process.
- No repeated gateway error loop.

## Live Post-Restart Smoke

After owner-approved restart of the existing service:

```bash
pgrep -af 'kolibri-telegram-gateway|ops/telegram_gateway.py'
journalctl -u kolibri-telegram-gateway.service -n 120 --no-pager
```

Expected:

- One matching process.
- One receiver-plan log with `startup_action=poll`.
- No `deleteWebhook` action.
- No `webhook_configured=true`.
- No sustained `telegram_gateway_error` events.

Owner-facing smoke:

- Owner sends one normal message or `/status` to `@kolibriai_bot`.
- Exactly one coherent response is observed.
- No duplicate replies are observed.
- A task-producing message creates at most one Control Plane task envelope.

## Rollback Smoke

After rollback to the prior main checkout:

```bash
pgrep -af 'kolibri-telegram-gateway|ops/telegram_gateway.py'
journalctl -u kolibri-telegram-gateway.service -n 80 --no-pager
```

Expected:

- One receiver.
- Same state path.
- No duplicate owner replies.
- No lost-control error loop.
