# Operator Actions

Task: `P0_TELEGRAM_PR89_MAIN_RECEIVER_CUTOVER_PLAN_2026_07_01`

This is a read-only action plan. These commands are for the approved live
operator window, not for this artifact task.

## Approval Gates

- Owner approves that PR #89 is ready for a controlled receiver cutover.
- Owner confirms the target bot is `@kolibriai_bot`.
- Owner confirms main is currently the active long-polling receiver.
- Owner confirms no Telegram runtime mutation is allowed during preflight.
- Owner approves any service restart in a named maintenance window.
- Owner separately approves any webhook migration. Without that approval,
  `TELEGRAM_ALLOW_WEBHOOK_DELETE` must remain unset.

## Preflight Checks

Run on the live host:

```bash
systemctl status kolibri-telegram-gateway.service --no-pager
pgrep -af 'kolibri-telegram-gateway|ops/telegram_gateway.py'
systemctl cat kolibri-telegram-gateway.service
journalctl -u kolibri-telegram-gateway.service -n 80 --no-pager
```

Expected:

- Exactly one gateway process.
- Service is `kolibri-telegram-gateway.service`.
- `ExecStart=/usr/local/bin/kolibri-telegram-gateway`.
- State path is `/var/lib/kolibri-telegram-gateway/state.json`.
- No evidence of a second poller or webhook receiver.

## In-Place Cutover Sequence

1. Stop if preflight does not prove exactly one receiver.
2. Update the existing `/opt/kolibri-ai-platform` checkout to the approved PR
   #89 commit. Do not clone or launch a second checkout.
3. Install updated files/scripts into the same paths used by the current
   service.
4. Ensure the service environment has `TELEGRAM_UPDATE_RECEIVER=polling`.
5. Ensure `TELEGRAM_ALLOW_WEBHOOK_DELETE` is unset.
6. Run `systemctl daemon-reload` if the unit file changed.
7. Restart only `kolibri-telegram-gateway.service`.
8. Immediately inspect logs for the redacted receiver plan.

Expected first receiver-plan log:

```json
{
  "event": "telegram_receiver_plan",
  "receiver_id": "kolibri-telegram-gateway",
  "mode": "polling",
  "should_poll": true,
  "webhook_configured": false,
  "conflict": null,
  "startup_action": "poll"
}
```

Abort if `startup_action` is `delete_webhook_then_poll` or if
`webhook_configured` is `true`.

## Actions Forbidden During This Cutover

- Do not run a second `kolibri-telegram-gateway`.
- Do not run manual `getUpdates` loops.
- Do not start a Mac-local Telegram receiver.
- Do not start a verifier receiver.
- Do not call `deleteWebhook`.
- Do not call `setWebhook`.
- Do not call Telegram send/edit methods from automation during preflight.
- Do not rotate `TELEGRAM_BOT_TOKEN`.
- Do not drop pending updates.
- Do not push to `main` from the live host.
