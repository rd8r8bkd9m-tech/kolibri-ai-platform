# P0 Telegram Single Canonical Receiver Migration Plan

Task: `P0_TELEGRAM_SINGLE_CANONICAL_RECEIVER_MIGRATION_2026_07_01`
Agent: `Мария — Telegram Receiver Steward`
Node: `home-live` lease on `plastilin`
Date: `2026-07-01`

## Objective

Classify the current update receiver topology for `@kolibriai_bot` across `home-live`, `home`, and `primary-candidate`, then stop/disable a Telegram receiver only if a single stale Kolibri long-polling worker is proven through an already authorized server path.

## Guardrails

- Do not call Bot API `getUpdates`.
- Do not rotate Telegram tokens.
- Do not drop or consume pending Telegram updates.
- Do not print Telegram tokens, owner chat IDs, cookies, passwords, private messages, or API keys.
- Do not stop canonical or ambiguous services.
- Do not modify product code.
- Do not push git changes.
- Keep PR #89 draft unless single canonical receiver is proven and an owner-approved live-switch command is returned.

## Evidence Plan

1. Read the task envelope and exact artifact contract from Control Plane.
2. Confirm Control Plane health and node inventory for `home-live`, `home`, and `primary-candidate`.
3. On the local `plastilin` host that represents both `home-live` and `home`, collect redacted evidence:
   - Bot API `getMe` and `getWebhookInfo` only.
   - `systemctl` service state for Telegram gateway units.
   - process, tmux, Docker, and n8n evidence.
   - stale PID file checks.
4. Attempt non-interactive authorized access to `primary-candidate` without passwords.
5. Stop/disable nothing unless the stale worker proof is exact and ownership is unambiguous.

## Classification Criteria

- Canonical production recommendation: webhook receiver integrated with Fabric/Control Plane.
- Polling is acceptable only as an emergency/bootstrap fallback.
- If webhook is unset and no authorized host-level proof identifies the active poller, classify as blocked/ambiguous.
- If a PID file points to a non-existing PID, classify the PID file as stale evidence only, not a live worker.
