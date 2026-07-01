# PR #89 Main Receiver Cutover Plan

Task: `P0_TELEGRAM_PR89_MAIN_RECEIVER_CUTOVER_PLAN_2026_07_01`

Date: 2026-07-01

Scope: read-only controlled cutover plan for PR #89 after main was confirmed as
the active long-polling receiver for `@kolibriai_bot`.

## Non-Negotiable Receiver Rule

`@kolibriai_bot` must have exactly one live update receiver at every point in the
rollout.

The existing main receiver is the systemd service
`kolibri-telegram-gateway.service`, running `/usr/local/bin/kolibri-telegram-gateway`
from `/opt/kolibri-ai-platform` with state at
`/var/lib/kolibri-telegram-gateway/state.json`.

Cutover must update that existing service in place. It must not start a second
polling process, Mac-local poller, verifier poller, one-off `getUpdates` loop, or
parallel webhook receiver.

## Current Main Receiver Contract

Main implements a single long-polling gateway in `ops/telegram_gateway.py`:

- `TelegramClient.get_updates()` calls Telegram `getUpdates` with
  `allowed_updates=["message"]`.
- `Gateway.run()` loops over `run_once()`.
- `run_once()` reads the persisted offset from `TELEGRAM_GATEWAY_STATE`, advances
  it to `update_id + 1`, saves state, and then polls tracked task transitions.
- Systemd uses a single `ExecStart=/usr/local/bin/kolibri-telegram-gateway`.
- The service has one persisted state path:
  `/var/lib/kolibri-telegram-gateway/state.json`.
- There is no receiver-mode guard in main; startup always instantiates
  `TelegramClient` and begins polling after owner IDs are validated.

## PR #89 Receiver Contract

PR #89 keeps the same gateway entry point, state path, and systemd `ExecStart`.
It adds a receiver planning layer in `ops/telegram_superfactory.py` and imports
it from `ops/telegram_gateway.py`.

Receiver-mode behavior added by PR #89:

- `TELEGRAM_UPDATE_RECEIVER=polling`: polling gateway owns updates.
- `TELEGRAM_UPDATE_RECEIVER=webhook`: gateway refuses to poll.
- `TELEGRAM_UPDATE_RECEIVER=disabled`: gateway refuses to poll.
- If Telegram reports an existing webhook while mode is `polling`, PR #89
  refuses to poll unless `TELEGRAM_ALLOW_WEBHOOK_DELETE=1`.
- If `TELEGRAM_ALLOW_WEBHOOK_DELETE=1`, startup plans
  `delete_webhook_then_poll` and calls `deleteWebhook(drop_pending_updates=False)`.
- Systemd gains `Environment=TELEGRAM_UPDATE_RECEIVER=polling`.

PR #89 also adds the Superfactory Mini App and runner contracts:

- `frontend/public/telegram-miniapp.html`
- `ops/telegram_superfactory.py`
- Control Plane endpoints for `/v1/superfactory/status`,
  `/v1/superfactory/tasks`, and task artifacts.
- Runner policy for `codex,mimo,api,local_llm`.
- Docs in `docs/telegram-superfactory.md` and run artifacts under
  `docs/agent/runs/2026-07-01-p0-pr89-telegram-superfactory-verifier-cleanup/`.

## Controlled Cutover

1. Confirm owner approval for a read-only preflight.
2. Confirm the live service identity without restarting it:
   `systemctl status kolibri-telegram-gateway.service --no-pager`.
3. Confirm there is exactly one gateway process without starting anything:
   `pgrep -af 'kolibri-telegram-gateway|ops/telegram_gateway.py'`.
4. Confirm no Mac-local or verifier receiver process is running. Any extra
   receiver is a hard stop; do not continue until the owner approves cleanup.
5. Confirm the deployed path is the existing gateway path
   `/opt/kolibri-ai-platform` and the state file remains
   `/var/lib/kolibri-telegram-gateway/state.json`.
6. Prepare PR #89 on the server by updating the existing checkout only. Do not
   clone a second runtime checkout and do not launch a parallel service.
7. Keep `TELEGRAM_UPDATE_RECEIVER=polling` on the existing
   `kolibri-telegram-gateway.service`.
8. Do not set `TELEGRAM_ALLOW_WEBHOOK_DELETE=1` for this cutover because main is
   already confirmed as the active long-polling receiver. If PR #89 logs
   `webhook_configured=true` or `startup_action=delete_webhook_then_poll`, abort.
9. Restart only the existing `kolibri-telegram-gateway.service` during the
   approved maintenance window. Do not start a second service or manual poller.
10. Watch the first startup log for a single redacted receiver plan with
    `receiver_id=kolibri-telegram-gateway`, `mode=polling`,
    `should_poll=true`, `webhook_configured=false`, and `startup_action=poll`.

## Abort Conditions

Abort before live rollout if any of these are true:

- More than one Telegram receiver process is found.
- Any service other than the existing `kolibri-telegram-gateway.service` is set
  to call `getUpdates` for `@kolibriai_bot`.
- PR #89 would execute `deleteWebhook`.
- PR #89 would refuse polling because a webhook is configured.
- The state file path changes or is missing.
- Owner approval is not explicit for the rollout window.
- Smoke checks fail or logs show repeated `telegram_gateway_error` events.

## Rollback

Rollback must preserve exactly one receiver:

1. Use the existing service only. Do not start a temporary poller.
2. Revert the deployed checkout on the server to the previous main commit that
   was running before cutover.
3. Run `systemctl daemon-reload` only if the service file changed.
4. Restart the existing `kolibri-telegram-gateway.service` once.
5. Confirm one process and the same state file path.
6. Confirm owner-visible `/status` or a plain owner message receives one
   coherent response.

Rollback must not rotate the Telegram token, delete pending updates, call
`deleteWebhook`, call `setWebhook`, or create a second receiver.

## PR #89 Live Rollout Decision

PR #89 should not be rolled out live unchanged until the receiver startup path is
made safer for the already-polling-main case.

Required before live rollout:

- Add an operator gate that prevents `deleteWebhook` from being reachable during
  the standard polling cutover, or split webhook migration into a separate
  explicit command/runbook outside normal gateway startup.
- Add/keep tests proving that default polling with no webhook never calls
  `deleteWebhook`, and that webhook deletion requires an explicit owner-approved
  migration mode.
- Update PR #89 deployment docs so the live command sequence says "update the
  existing receiver in place" and does not imply running any second poller.

After those changes, PR #89 can be rolled out with the controlled in-place
service update above.
