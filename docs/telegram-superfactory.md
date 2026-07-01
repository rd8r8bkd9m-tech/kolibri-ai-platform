# Telegram Superfactory Command Layer

## Contract

`@kolibriai_bot` has exactly one canonical update receiver: `kolibri-telegram-gateway`.
The gateway is API-first: Telegram messages become Control Plane task envelopes and
remote Agent Host runners execute Codex, MIMO, API, local LLM, or image work.

The Mac is only a dispatcher. It must not run a second Telegram poller.

## Receiver Modes

- `TELEGRAM_UPDATE_RECEIVER=polling`: systemd gateway owns `getUpdates`.
- `TELEGRAM_UPDATE_RECEIVER=webhook`: the polling gateway refuses to start.
- `TELEGRAM_UPDATE_RECEIVER=disabled`: no update receiver starts.

If Telegram already has a webhook while `polling` is configured, startup refuses
to poll. To migrate from webhook to polling, set `TELEGRAM_ALLOW_WEBHOOK_DELETE=1`
for a single restart, confirm the gateway deletes the webhook, then remove it.

## Mini App

The Mini App entry is `frontend/public/telegram-miniapp.html`.
It calls:

- `GET /v1/superfactory/status`
- `POST /v1/superfactory/tasks`
- `GET /v1/superfactory/tasks/{task_id}/artifacts`

Every Mini App request must send `X-Telegram-Init-Data`. The Control Plane
validates Telegram Web App `initData`, checks freshness, and allows only
`TELEGRAM_OWNER_IDS` or `TELEGRAM_ADMIN_IDS`.

## Runner Policy

`KOLIBRI_RUNNER_POLICY` defaults to `codex,mimo,api,local_llm`.

The selected runner and diagnostics are included in task envelopes. Missing API
or local LLM configuration is reported as missing environment names only; token
values, private prompts, cookies, chat IDs, and owner messages are not printed.

## Live Deployment

1. Push this branch; do not push to `main`.
2. On the server, pull the branch into `/opt/kolibri-ai-platform`.
3. Install scripts/services without editing `/etc/kolibri/telegram.env` in logs.
4. Run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart kolibri-factory-control.service
sudo systemctl restart kolibri-agent-host.service
sudo systemctl restart kolibri-telegram-gateway.service
sudo journalctl -u kolibri-telegram-gateway.service -n 50 --no-pager
```

Do not start any Mac-local poller and do not run another `getUpdates` process.

## Rollback

1. Stop the gateway on the server:

```bash
sudo systemctl stop kolibri-telegram-gateway.service
```

2. Check out the previous release branch on the server.
3. Restart `kolibri-factory-control.service` and `kolibri-telegram-gateway.service`.
4. If rollback returns to webhook mode, set the webhook once from the server-side
   deployment job only. Do not run polling at the same time.

## Safety Notes

- Never print `TELEGRAM_BOT_TOKEN`, owner chat IDs, API keys, cookies, passwords,
  private Telegram messages, or raw logs in owner-facing responses.
- Owner dialogue is generated in Russian from factory context and project memory.
- Raw paths, logs, task IDs, node IDs, and artifact paths are hidden unless the
  owner explicitly asks for technical evidence.
