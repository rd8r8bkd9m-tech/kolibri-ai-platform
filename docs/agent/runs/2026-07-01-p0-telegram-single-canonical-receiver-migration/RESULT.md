# P0 Telegram Single Canonical Receiver Migration Result

Task: `P0_TELEGRAM_SINGLE_CANONICAL_RECEIVER_MIGRATION_2026_07_01`
Agent: `Мария — Telegram Receiver Steward`
Node: `home-live` lease on `plastilin`

## Outcome

Blocked, no runtime mutation performed.

The current topology could not be proven to have exactly one stale Kolibri Telegram long-polling worker. Therefore no service was stopped or disabled.

## Receiver Topology Classification

### `@kolibriai_bot` platform state

- Bot identity: `kolibriai_bot`.
- Webhook URL: empty.
- Pending updates: `0`.
- Read-only Bot API methods used: `getMe`, `getWebhookInfo`.
- Bot API methods not used: `getUpdates`, `setWebhook`, `deleteWebhook`.

Interpretation: no webhook is registered. If the live bot is responding, the active receiver is long polling somewhere outside the proven local gateway evidence.

### `home-live`

- Control Plane: online as `home-live` on `plastilin`.
- Systemd:
  - `kolibri-telegram-gateway.service`: loaded, inactive/dead, disabled, `MainPID=0`.
  - `kolibri-telegram-processor.service`: not found.
- Container evidence: n8n-style containers are running, but n8n DB has no workflows or webhook rows.
- tmux/process evidence: no live Kolibri Telegram receiver process.
- Stale evidence:
  - `/srv/kolibri/repo/.factory/runs/telegram-gateway.pid` points to a non-existing PID.
  - `/srv/kolibri/repo/.factory/runs/telegram-processor.pid` points to a non-existing PID.

Classification: no active receiver proven on `home-live`.

### `home`

- Control Plane: online as `home` on the same `plastilin` host.
- Systemd/process/container/tmux evidence is the same local host evidence as `home-live`.
- n8n evidence: no workflows, no webhook rows, no Telegram workflow node ownership.

Classification: no active receiver proven on `home`.

### `primary-candidate`

- Control Plane: online as `primary-candidate`, hostname `kolibri`.
- Host-level inspection blocked:
  - `primary-candidate` SSH alias not resolvable.
  - Direct SSH to reachable control-plane IPs denied authentication.
  - No Control Plane remote exec endpoint exposed to this lease.

Classification: unknown/blocked. `primary-candidate` may still host the active long-polling receiver, but this lease cannot prove or repair it.

## Action Taken

Read-only classification only.

No service was stopped, disabled, restarted, or edited.

## Blockers

- No authorized shell path to `primary-candidate`.
- No passwordless sudo on `plastilin`, so root-only service environment and journal inspection are unavailable.
- The checked-out repository is missing the requested `read_first` Telegram gateway docs/source paths; live copies exist outside this worktree and were used only as read-only runtime context.
- The actual active long-polling receiver remains not discovered from this lease.

## Canonical Production Recommendation

Use exactly one canonical production receiver:

- Preferred: Telegram webhook receiver integrated with Fabric/Control Plane.
- Emergency/bootstrap fallback only: a single supervised long-polling gateway.

Do not run webhook and long polling concurrently for the same bot.

## PR #89 Status

PR #89 must remain draft.

This task did not prove a single canonical receiver and did not return an owner-approved live-switch command.

## Remote Result

```json
{
  "task_id": "P0_TELEGRAM_SINGLE_CANONICAL_RECEIVER_MIGRATION_2026_07_01",
  "node": "home-live",
  "agent_display_name": "Мария — Telegram Receiver Steward",
  "action_taken": "read_only_topology_classification; no_service_mutation",
  "blockers": [
    "primary-candidate host-level access unavailable from lease",
    "no Control Plane remote exec endpoint exposed",
    "no passwordless sudo for root-only local service environment or journal inspection",
    "active long-polling receiver not proven"
  ],
  "fallback_nodes": [
    "primary-candidate",
    "home-live",
    "home"
  ],
  "next_task": "OWNER_PRIMARY_CANDIDATE_TELEGRAM_RECEIVER_PROBE_AND_REPAIR_2026_07_01"
}
```
