# DEPLOY_RUNBOOK

## Runtime unit draft

Tracked unit:

```text
ops/systemd/kolibri-chatgpt-action-gateway.service
```

Default local bind:

```text
127.0.0.1:9197
```

Required env:

```text
KOLIBRI_CHATGPT_ACTION_TOKEN
KOLIBRI_FACTORY_CONTROL_URLS=http://10.99.0.10:9101,http://10.99.0.2:9101,http://10.99.0.1:9101
KOLIBRI_CHATGPT_ACTION_TIMEOUT=4
```

## Owner-approved deploy commands

```bash
sudo install -m 0755 ops/chatgpt_action_gateway.py /srv/kolibri-ai-platform/ops/chatgpt_action_gateway.py
sudo install -m 0644 ops/systemd/kolibri-chatgpt-action-gateway.service /etc/systemd/system/kolibri-chatgpt-action-gateway.service
sudo install -d -m 0750 /etc/kolibri
sudoedit /etc/kolibri/chatgpt-action-gateway.env
sudo systemctl daemon-reload
sudo systemctl enable --now kolibri-chatgpt-action-gateway.service
curl -fsS http://127.0.0.1:9197/v1/action/health
```

Do not paste the token into shell history. Store it only in `/etc/kolibri/chatgpt-action-gateway.env`.

## Public Action URL

Production target:

```text
https://action.kolibriai.ru
```

Put nginx or Cloudflare Tunnel in front of `127.0.0.1:9197`. TLS must terminate before ChatGPT Builder uses the Action.

## Rollback

```bash
sudo systemctl disable --now kolibri-chatgpt-action-gateway.service
sudo rm -f /etc/systemd/system/kolibri-chatgpt-action-gateway.service
sudo systemctl daemon-reload
```

## Current blocker

No runtime deploy was performed in this task. Owner approval is required before installing service files or exposing `https://action.kolibriai.ru`.
