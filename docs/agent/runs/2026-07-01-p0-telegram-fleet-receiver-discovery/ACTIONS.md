# P0 Telegram Fleet Receiver Discovery Actions

## Read-Only Inventory

- Queried Control Plane `/v1/nodes` through `ops/kolibri-dispatch nodes`.
- Queried this task envelope and predecessor tasks through
  `ops/kolibri-dispatch status`.
- Read `ops/orchestrator_roster.py` node cards.
- Read `ops/telegram_gateway.py` and
  `ops/systemd/kolibri-telegram-gateway.service`.

Inventory facts:

- Control Plane reported 42 registered nodes, 21 fresh nodes, and 20 fresh
  canonical nodes.
- Allowed probe nodes from the task envelope:
  `home`, `primary-candidate`, `home-live`, `main`, `mesh-9fts`,
  `mesh-agent-01`, `mesh-agent-02`, `mesh-agent-03`.
- Avoided nodes from the task envelope: `qjns`, `uiap`.

## Task History Used

- `P0_TELEGRAM_SINGLE_CANONICAL_RECEIVER_MIGRATION_2026_07_01`
  - State: `completed`
  - Target: `home-live`
  - Known evidence in the current task envelope: completed but
    blocked/ambiguous; no active receiver on `home`/`home-live`; webhook URL
    empty; `pending_update_count=0`.
- `P0_PRIMARY_CANDIDATE_TELEGRAM_RECEIVER_PROBE_AND_REPAIR_2026_07_01`
  - State: `failed`
  - Target: `primary-candidate`
  - Known evidence in the current task envelope: failed wrapper but useful
    evidence; gateway inactive/disabled; no visible active receiver on
    `primary-candidate`; prior receiver conflict indicated another receiver
    likely existed.
- `P0_TELEGRAM_ACTIVE_POLLER_DIAGNOSTIC_AND_REPAIR_2026_07_01`
  - State: `failed`
  - Target: `home-live`
  - Used only as historical context.

## Filesystem Manifest Evidence

Path/name-only manifest checks:

- Found prior `P0_TELEGRAM_SINGLE_CANONICAL_RECEIVER_MIGRATION_2026_07_01`
  artifact manifest under the `home-live` artifact root.
- Found prior `P0_TELEGRAM_ACTIVE_POLLER_DIAGNOSTIC_AND_REPAIR_2026_07_01`
  artifact manifest under the `home-live` artifact root.
- Found multiple historical `TGCHAT-*` and `TG-*` artifact/worktree paths on
  `home` and `home-live`; these are task artifacts, not receiver processes.
- No local primary-candidate artifact manifest was accessible from this
  worktree host.

## Host Probes

### `home` / `home-live`

- Hostname: `plastilin`.
- Local `/etc/kolibri/telegram.env` was readable, but values were not printed.
- `/var/lib/kolibri-telegram-gateway/state.json` was missing.
- `kolibri-telegram-gateway.service` was loaded but inactive/dead and disabled.
- Process scan found `director-home-live` agent host with `telegram`
  capability, but no `kolibri-telegram-gateway` receiver process.
- Process scan also found an older filesystem-search command containing
  Telegram search markers; classified as unrelated probe noise, not a receiver.

### `main`

- SSH target: `root@10.99.0.2`.
- Hostname: `kolibri-main-api`.
- `kolibri-telegram-gateway.service`:
  - LoadState: `loaded`
  - ActiveState: `active`
  - SubState: `running`
  - MainPID: `2186292`
  - UnitFileState: `disabled`
  - EnvironmentFiles: `/etc/kolibri/telegram.env`
  - ExecStart: `/usr/local/bin/kolibri-telegram-gateway`
  - User/Group: `kolibri`
- Receiver state file existed and had a fresh mtime during the probe.
- State-file metadata only:
  - Top-level keys: `common_chat_since`, `memory`, `mesh_seen_messages`,
    `offset`, `owner_chat_id`, `tracked`
  - Offset present: `122392218`
  - Mtime age during probe: about 15 seconds
- Process scan found:
  - `python3 /usr/local/bin/kolibri-telegram-gateway`
  - `python3 /usr/local/bin/kolibri-telegram-mesh-outbound-relay`
- No private state contents were recorded.

### `primary-candidate`

- SSH target: `root@10.99.0.10`.
- Current direct SSH probe returned permission denied.
- Classification uses predecessor task evidence from the current task envelope:
  gateway inactive/disabled and no visible active receiver.

### `mesh-9fts`

- SSH target: `root@10.99.0.5`.
- Hostname: `kolibri-inference-recovery`.
- `kolibri-telegram-gateway.service` was not found.
- Gateway state file was missing.
- Process scan found an old Mimo owner task launched from a Telegram request,
  but not a receiver process.
- Container scan found unrelated infrastructure container `amnezia-awg2`.

### `mesh-agent-01`, `mesh-agent-02`, `mesh-agent-03`

- `mesh-agent-01` SSH returned permission denied.
- `mesh-agent-02` bounded SSH probe timed out.
- `mesh-agent-03` bounded SSH probe timed out.
- Control Plane records for these nodes were fresh/degraded but did not expose a
  Telegram receiver process.

## Bot API Checks

Only redacted `getWebhookInfo` was called.

- Local `home` token:
  - `ok=true`
  - `has_webhook_url=false`
  - `pending_update_count=0`
  - `allowed_updates_count=1`
- `main` token:
  - `ok=true`
  - `has_webhook_url=false`
  - `pending_update_count=0`
  - `allowed_updates_count=1`
- Normalized token material for `home` and `main` did not match.
  The token values and token hashes were not printed.

## Actions Not Taken

- No service was stopped.
- No Telegram state-changing Bot API method was called.
- No product code was modified.
- No central GitHub push was performed.
- PR #89 was left untouched.
