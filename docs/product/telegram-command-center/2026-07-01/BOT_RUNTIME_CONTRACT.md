# Telegram Bot Runtime Contract

Task: `P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01`

This file is the exact-path relay of the remote docs-only audit. The detailed
source material is in `COMMAND_CENTER_SPEC.md` and `TELEGRAM_RUNTIME_GAP_AUDIT.md`.

## Contract

- The bot is an owner-facing command router over Fabric API / Control Plane, not
  a shell and not the source of truth.
- The production receiver must have exactly one active owner for one bot token.
  Webhook is preferred for stable ingress; long polling is fallback only.
- No startup path may call `getUpdates`, `setWebhook`, `deleteWebhook`,
  `setMyCommands`, `setChatMenuButton`, or restart services unless the task is
  an explicit owner-approved migration task.
- User-facing replies must be human Russian summaries grounded in factory state.
  Raw node IDs, paths, logs, stderr, tokens, owner prompts, and internal leases
  are hidden unless explicitly requested and redacted.
- Task submission must create a Control Plane envelope with `task_id`,
  `trace_id`, owner/source metadata, write scope, constraints, required
  artifacts, and review expectations.
- Every Telegram-originated task must be visible in task ledger, artifact
  manifest, and GitHub/PR state when code or docs are changed.

## Required Implementation Order

1. Auth/session contract.
2. Read-only command center APIs.
3. Mini App read-only shell.
4. Command composer and task submit.
5. Safe task actions.
6. PR/CI/artifact views.
7. Rich report renderer.
8. Streaming.

Guest, Bot-to-Bot, Business, Stars, payments, gifts, and managed bots remain
disabled until separate policy PRs exist.
