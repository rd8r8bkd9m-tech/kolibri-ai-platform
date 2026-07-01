# P0 Primary Candidate Telegram Receiver Probe Result

Task: `P0_PRIMARY_CANDIDATE_TELEGRAM_RECEIVER_PROBE_AND_REPAIR_2026_07_01`

Control Plane status:
- `failed`

Useful remote classification:
- `primary-candidate` does **not** currently own a visible active
  `@kolibriai_bot` long-polling receiver.
- The canonical `kolibri-telegram-gateway.service` exists but is `inactive`
  and `disabled`.
- The same service previously logged `TELEGRAM_GETUPDATES_CONFLICT`, so another
  receiver likely existed recently, but this probe did not prove a stale
  non-canonical worker on primary-candidate.
- No service, process, container or tmux session was stopped or disabled.

Remote blocker:
- `active_receiver_owner_not_proven_on_primary_candidate`

Implication:
- `home`, `home-live` and `primary-candidate` do not currently prove ownership
  of the live receiver.
- Since `@kolibriai_bot` has no webhook configured and still responds, the
  active long-polling owner is likely on another token-capable, control-plane,
  legacy or manually launched host/process.

PR #89:
- Must remain draft.
- Do not live-switch or enable a new receiver yet.

Runner contract note:
- The remote task again produced useful evidence but failed the wrapper because
  exact run artifact paths were not honored.
- This reinforces the P0 Agent Host runner contract hardening requirement.
