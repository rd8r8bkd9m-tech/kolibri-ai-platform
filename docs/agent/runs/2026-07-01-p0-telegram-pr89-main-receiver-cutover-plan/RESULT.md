# Result

Task: `P0_TELEGRAM_PR89_MAIN_RECEIVER_CUTOVER_PLAN_2026_07_01`

Status: read-only cutover plan prepared.

## Evidence Reviewed

- Current branch started at `origin/main` commit
  `6d0317c52a9694448ee2c352dc196ce7a27b9487`.
- PR #89 was fetched read-only as `origin/pr/89`.
- PR #89 head reviewed:
  `2b7cec1 docs: add pr89 exact run artifacts`.
- PR #89 branch reviewed:
  `origin/p0/telegram-superfactory-bot-miniapp-2026-07-01`.

## Main vs PR #89 Summary

Main:

- One long-polling receiver in `ops/telegram_gateway.py`.
- One systemd service, `kolibri-telegram-gateway.service`.
- One state path, `/var/lib/kolibri-telegram-gateway/state.json`.
- No receiver-mode guard.

PR #89:

- Keeps the same gateway service and state path.
- Adds `TELEGRAM_UPDATE_RECEIVER=polling` to the service unit.
- Adds `plan_update_receiver()` and redacted receiver status logging.
- Refuses polling when webhook mode is selected or a webhook conflict exists.
- Adds a one-time webhook deletion path behind
  `TELEGRAM_ALLOW_WEBHOOK_DELETE=1`.
- Adds Superfactory Mini App endpoints, runner selection, docs, and tests.

## Decision

PR #89 needs further changes before live rollout.

Reason: the normal gateway startup path now contains a reachable
`deleteWebhook(drop_pending_updates=False)` call when
`TELEGRAM_ALLOW_WEBHOOK_DELETE=1`. Even though the current cutover should keep
that variable unset because main is already the active long-polling receiver,
webhook migration should be separated from the standard live receiver startup or
made harder to trigger accidentally.

Minimum required PR #89 change:

- Make webhook deletion impossible during the standard polling cutover, or move
  it to a separate operator-approved migration command/runbook.

Recommended doc change:

- Update PR #89 deployment docs to say the existing
  `kolibri-telegram-gateway.service` is updated in place and no second receiver
  is started.

## Runtime Safety

This task did not:

- Start, stop, or restart Telegram services.
- Call Telegram API state-changing methods.
- Call `getUpdates`.
- Merge PR #89.
- Push to `main`.
- Modify product code.
- Print secrets.
