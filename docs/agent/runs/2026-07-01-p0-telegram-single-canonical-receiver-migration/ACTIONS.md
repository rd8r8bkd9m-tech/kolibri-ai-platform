# P0 Telegram Single Canonical Receiver Migration Actions

Task: `P0_TELEGRAM_SINGLE_CANONICAL_RECEIVER_MIGRATION_2026_07_01`
Agent: `Мария — Telegram Receiver Steward`
Node: `home-live` lease on `plastilin`

## Actions Taken

- Queried Control Plane health on:
  - `http://10.99.0.2:9101`
  - `http://10.99.0.10:9101`
  - `http://10.99.0.1:9101`
- Read the Control Plane task envelope and exact required artifact paths.
- Checked requested `read_first` files in the checked-out repository. They were missing from this worktree.
- Mapped node inventory:
  - `home-live`: `plastilin`, online in Control Plane.
  - `home`: `plastilin`, online in Control Plane.
  - `primary-candidate`: `kolibri`, online in Control Plane.
- Attempted SSH aliases `home-live`, `home`, and `primary-candidate`: all unresolved.
- Attempted direct non-interactive SSH to `10.99.0.2` and `10.99.0.10`: port 22 open, access denied by `publickey,password`.
- Confirmed local passwordless sudo is unavailable: `sudo -n true` exits non-zero.
- Collected local systemd state for `kolibri-telegram-gateway.service` and `kolibri-telegram-processor.service`.
- Collected local process, Docker, tmux, and n8n evidence using redaction.
- Used `/srv/kolibri/repo/ops/telegram.env` in memory to call read-only Bot API methods:
  - `getMe`
  - `getWebhookInfo`
- Did not call Bot API `getUpdates`.
- Did not stop, disable, restart, or edit any service.
- Did not rotate tokens.
- Did not modify product code.
- Did not push git changes.

## Redacted Evidence Summary

### Bot API

- `getMe` identified the token source as `@kolibriai_bot`.
- `getWebhookInfo` returned:
  - `url`: empty string
  - `pending_update_count`: `0`
  - `allowed_updates`: `["message"]`

Interpretation: no Telegram webhook is currently registered for `@kolibriai_bot`; pending updates were not consumed or dropped.

### home-live / home: systemd

Both `home-live` and `home` map to the same host, `plastilin`.

- `kolibri-telegram-gateway.service`
  - `LoadState=loaded`
  - `ActiveState=inactive`
  - `SubState=dead`
  - `UnitFileState=disabled`
  - `MainPID=0`
  - `ExecStart=/usr/local/bin/kolibri-telegram-gateway --control-url http://10.99.0.2:9101`
  - `EnvironmentFile=/etc/kolibri/telegram.env`
- `kolibri-telegram-processor.service`
  - `LoadState=not-found`
  - `ActiveState=inactive`
  - `SubState=dead`

The installed gateway unit is not the active receiver.

### home-live / home: process and tmux

- No live process matched the Kolibri Telegram receiver patterns:
  - `telegram_task_gateway`
  - `telegram_task_processor`
  - `telegram_gateway.py`
  - `kolibri-telegram-gateway`
- Two long-lived `grep`/shell processes from an earlier diagnostic contain Telegram search terms in their command lines. They are not Telegram receivers and were not stopped.
- tmux sessions observed: `codex-home`, `kolibri-dual-codex-mimo`, `kolibri-home-screen`, `mimo-home-screen`.
- No tmux pane was a Telegram gateway/poller.

### home-live / home: stale PID files

- `/srv/kolibri/repo/.factory/runs/telegram-gateway.pid` contained PID `74409`; `/proc/74409` does not exist.
- `/srv/kolibri/repo/.factory/runs/telegram-processor.pid` contained PID `4513`; `/proc/4513` does not exist.

Interpretation: stale PID files only; no live worker was proven.

### home-live / home: containers and n8n

Running containers include n8n-style `kolibri-fabrika` services:

- `kolibri-fabrika-kolibri-webhook-1`
- `kolibri-fabrika-kolibri-webhook-2`
- `kolibri-main`
- `kolibri-fabrika-kolibri-worker-1`
- `kolibri-fabrika-kolibri-worker-2`
- `kolibri-fabrika-kolibri-exporter-1`
- `kolibri-fabrika-postgres-1`
- `kolibri-fabrika-redis-1`

n8n database evidence from `kolibri-fabrika-postgres-1`:

- `workflow_entity`: `0` total workflows, `0` active workflows.
- `webhook_entity`: `0` rows.
- Telegram-like workflow node count: `0`.

Container env-name evidence shows `TELEGRAM_BOT_TOKEN` variables in the n8n-style containers, but those values are placeholders/invalid format and Bot API calls returned 404 when tested in memory. No n8n workflow ownership was proven.

### primary-candidate

- Control Plane inventory shows `primary-candidate` online with hostname `kolibri`.
- Host-level evidence is blocked:
  - SSH alias `primary-candidate` is not resolvable.
  - Direct SSH to reachable control-plane IPs is not authorized for this lease.
  - No Control Plane remote exec endpoint was found.

No service state, process list, tmux list, container list, or n8n database evidence could be collected from `primary-candidate`.

## Migration Decision

No service was stopped or disabled.

Reason: a single stale Kolibri Telegram long-polling worker was not proven. The local `home-live/home` gateway is inactive/disabled and stale PID files are not live workers. `primary-candidate` remains inaccessible for host-level inspection, so ownership is ambiguous.
