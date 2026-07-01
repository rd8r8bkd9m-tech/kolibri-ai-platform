# P0 Telegram Single Canonical Receiver Migration Next Steps

Task: `P0_TELEGRAM_SINGLE_CANONICAL_RECEIVER_MIGRATION_2026_07_01`
Agent: `Мария — Telegram Receiver Steward`

## Blocker Classification

Ownership is ambiguous because `@kolibriai_bot` has no webhook configured, local `home-live/home` has no active receiver, and `primary-candidate` host-level evidence is inaccessible from this lease.

No migration is safe until the active long-polling owner is proven.

## Fallback Route

Use an owner-authorized shell on `primary-candidate` or dispatch a new Control Plane task to a node with verified host-level execution on `primary-candidate`.

Suggested next task:

`OWNER_PRIMARY_CANDIDATE_TELEGRAM_RECEIVER_PROBE_AND_REPAIR_2026_07_01`

## Next Owner-Safe Probe Command

Run this on `primary-candidate` through an owner-approved privileged shell. It is read-only and does not call `getUpdates`.

```sh
set -eu
echo "== host =="
hostname
date -u +%FT%TZ

echo "== systemd =="
systemctl show kolibri-telegram-gateway.service \
  -p LoadState -p ActiveState -p SubState -p UnitFileState -p FragmentPath -p ExecStart -p MainPID --no-pager 2>&1 || true
systemctl show kolibri-telegram-processor.service \
  -p LoadState -p ActiveState -p SubState -p UnitFileState -p FragmentPath -p ExecStart -p MainPID --no-pager 2>&1 || true

echo "== process =="
pgrep -af '[t]elegram_task_gateway|[t]elegram_task_processor|[t]elegram_gateway.py|[k]olibri-telegram-gateway|[g]etUpdates|[n]ode-telegram-bot-api|[t]elegraf|[g]rammy' || true

echo "== containers =="
docker ps --no-trunc --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Command}}' 2>/dev/null \
  | grep -Ei 'telegram|kolibri|n8n|bot|webhook|worker' || true

echo "== tmux =="
tmux list-panes -a -F '#{session_name}:#{window_index}.#{pane_index}\t#{pane_current_command}\t#{pane_current_path}\t#{pane_title}' 2>/dev/null \
  | grep -Ei 'telegram|kolibri|n8n|bot|gateway|factory' || true
```

Before sharing output, redact:

- Telegram tokens.
- owner chat IDs.
- cookies.
- passwords.
- private messages.
- API keys.

## Conditional Repair Command

Only after the probe proves one stale non-canonical Kolibri Telegram long-polling unit and no canonical receiver, the owner may run the exact service repair for that proven stale unit:

```sh
sudo systemctl stop kolibri-telegram-gateway.service
sudo systemctl disable kolibri-telegram-gateway.service
systemctl show kolibri-telegram-gateway.service \
  -p LoadState -p ActiveState -p SubState -p UnitFileState -p MainPID --no-pager
```

Do not run the repair command if the unit is canonical, if it is the only intended emergency/bootstrap receiver, or if the active receiver identity is still ambiguous.

## Canonical Live Switch

No owner-approved live-switch command is returned by this task.

Recommended future switch after ownership is proven:

- Register exactly one webhook receiver integrated with Fabric/Control Plane.
- Keep long polling disabled except for a documented emergency/bootstrap fallback.
- Confirm with `getWebhookInfo`; do not use `getUpdates` during verification.
