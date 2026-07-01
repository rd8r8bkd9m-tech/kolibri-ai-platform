# Owner Auth And InitData Policy

Task: `P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01`

## Policy

- Verify `Telegram.WebApp.initData` on the backend before creating a session.
- Treat `initDataUnsafe` as display-only until verified `initData` proves the
  same Telegram user.
- Reject missing, malformed, stale, replayed, or signature-invalid init data.
- Map verified users to Kolibri roles: `owner`, `operator`, `reviewer`,
  `observer`, and `guest_candidate`.
- Use short-lived sessions. Recommended default: 15 minutes idle TTL and 8 hours
  absolute max.
- Telegram Login/OIDC may support non-Mini-App web access, but must share the
  same role mapping, replay checks, TTL, audit log, and redaction rules.

## Privilege Rules

- `owner`: submit tasks and approve gated actions.
- `operator`: submit bounded tasks.
- `reviewer`: inspect and review.
- `observer`: read-only.
- `guest_candidate`: no factory access until elevated.

No Telegram user can become `owner` by public profile fields, username, chat
membership, or Mini App client data alone.
