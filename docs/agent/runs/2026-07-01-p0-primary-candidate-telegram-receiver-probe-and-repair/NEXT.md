# P0 Primary Candidate Telegram Receiver Probe Next

Next task:

`P0_TELEGRAM_FLEET_RECEIVER_DISCOVERY_2026_07_01`

Goal:

Find the actual active `@kolibriai_bot` long-polling receiver across remaining
token-capable, control-plane, legacy and manually launched hosts.

Constraints:

- No `getUpdates`.
- No `setWebhook`.
- No `deleteWebhook`.
- No token rotation.
- No pending update deletion.
- No product code modification.
- No service stop/disable unless exactly one stale non-canonical receiver is
  proven.
- All output must be redacted.

Why:

The known high-probability nodes have now been checked:

- `home/home-live`: no active Kolibri Telegram receiver; webhook empty;
  pending updates `0`.
- `primary-candidate`: canonical gateway inactive/disabled; no visible active
  local receiver.

Therefore the remaining correct move is fleet-wide receiver discovery, not live
switching PR #89.
