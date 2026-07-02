# Actions

Execution node:

- `hostname`: `kolibri`
- Execution class: server/control node, not local Mac implementation.
- Repository path:
  `/var/lib/kolibri-agent/worktrees/P0_TELEGRAM_MAIN_RECEIVER_METADATA_ACCESS_AND_SINGLE_RECEIVER_CUTOVER_GATE_2026_07_02/P0_TELEGRAM_MAIN_RECEIVER_METADATA_ACCESS_AND_SINGLE_RECEIVER_CUTOVER_GATE_2026_07_02-attempt-1/repo`

Read-only checks performed:

- Read prior receiver artifacts:
  - `docs/agent/runs/2026-07-01-p0-telegram-fleet-receiver-discovery/RESULT.md`
  - `docs/agent/runs/2026-07-01-p0-telegram-main-receiver-token-lineage-identity/RESULT.md`
  - `docs/agent/runs/2026-07-02-p0-deploy-factory-control-and-telegram-gateway-canary-repair/RESULT.md`
  - `docs/product/telegram-command-center/2026-07-01/BOT_RUNTIME_CONTRACT.md`
- Checked systemd metadata for `kolibri-telegram-gateway.service`.
- Checked process command line using `pgrep -af` without environment output.
- Checked `/var/lib/kolibri-telegram-gateway/state.json` file metadata and
  selected JSON key presence/counts only.
- Sourced `/etc/kolibri/telegram.env` locally without echoing it.
- Called Telegram Bot API read-only methods:
  - `getMe`
  - `getWebhookInfo`

Forbidden actions not performed:

- No `getUpdates`.
- No `setWebhook`.
- No `deleteWebhook`.
- No token rotation.
- No pending update deletion.
- No service start, stop, restart, enable, or disable.
- No product code modification.
- No git push.
- No secrets printed.
