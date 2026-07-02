# Tests

Verification commands run:

```bash
hostname
date -u +%Y-%m-%dT%H:%M:%SZ
systemctl show kolibri-telegram-gateway.service --property=LoadState,ActiveState,SubState,MainPID,User,Group,ExecStart,FragmentPath,UnitFileState,StateChangeTimestamp --no-pager
pgrep -af 'kolibri-telegram-gateway|telegram_gateway.py'
```

Read-only metadata probe:

```bash
bash -u <<'BASH'
set +x
ENV_FILE=/etc/kolibri/telegram.env
STATE_FILE=/var/lib/kolibri-telegram-gateway/state.json
# Checked env readability, state-file metadata, JSON key presence/counts,
# getMe, and getWebhookInfo. Token value was never printed.
BASH
```

Repository verification:

```bash
git diff --check
rg --no-ignore -n '[0-9]{6,}:[A-Za-z0-9_-]{20,}|[A-Za-z0-9_]*(TOKEN|SECRET|PASSWORD|COOKIE|API_KEY|CHAT_ID)=[^ ]+' docs/agent/runs/2026-07-02-p0-telegram-main-receiver-metadata-access-and-single-receiver-cutover-gate || true
```

Notes:

- The first API parser attempt failed locally with `NameError` because JSON was
  accidentally passed to Python as source text. It caused no Bot API mutation and
  printed no secret. The same read-only methods were rerun with a file-based
  parser and succeeded.
