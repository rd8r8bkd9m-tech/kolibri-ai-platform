# Telegram Mini App UX Spec

Task: `P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01`

The Mini App first screen is a command center, not a landing page.

## Screens

- Command composer: objective, task kind, target repo/project, capability,
  runner/model preference, priority, retry budget, review requirement,
  artifact expectations, safety gates, dry-run switch, submit.
- Task board: queued, running, waiting review, review, completed, failed,
  cancelled, dead-letter.
- Fleet: node health, capabilities, active task, drain state, CPU/RAM/disk,
  heartbeat freshness, role display name.
- Agents: agent id, node id, runner, supported task kinds, current lease, last
  heartbeat, latest sanitized result.
- Models: provider/model health, available local and external models, per-task
  model override, cost/rate warning.
- PR/CI: branch, PR URL, check runs, failure summaries, merge readiness.
- Artifacts: safe manifest, redacted logs, screenshots, generated images,
  document/report links.
- Settings: owner identity, roles, session TTL, notifications, theme, safe
  display mode, redaction preview.

## UX Requirements

- Use Telegram theme params, safe area/content safe area, fullscreen where
  useful, and native bottom buttons only for clear actions.
- All destructive or privileged actions require explicit confirmation in the
  same verified session.
- Loading, empty, error, blocked, partial, running, completed, and failed states
  must be distinct and readable on mobile.
- No raw logs or secrets appear in compact cards.
- Public/default users must not see owner controls.
