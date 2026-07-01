# Deployment Notes

This canonical run artifact preserves the deployment notes from the existing
PR #89 cleanup docs. It records the next operator command only; it does not
claim that a live deployment, token rotation, pending update deletion, or
receiver migration was performed.

Branch policy:

- Push only `p0/telegram-superfactory-bot-miniapp-2026-07-01`.
- Do not push to `main`.
- Do not force push.

Next deployment command:

```bash
sudo systemctl daemon-reload && sudo systemctl restart kolibri-factory-control.service kolibri-agent-host.service kolibri-telegram-gateway.service
```

Live Bot API cleanup notes preserved:

- Do not start a Mac-local poller.
- Do not run a second `getUpdates` receiver.
- Do not delete pending updates during verifier cleanup.
- Do not rotate the Telegram token during verifier cleanup.
- If migrating from webhook to polling later, use
  `TELEGRAM_ALLOW_WEBHOOK_DELETE=1` for a single operator-approved restart,
  verify the receiver state, then remove that setting.
