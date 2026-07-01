# PR Slice Plan

Task: `P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01`

## PR 1: Mini App Auth Contract

Changes:

- Backend Telegram `initData` verifier.
- Session TTL and role mapping.
- Redaction helpers for auth/session responses.
- Unit tests with fixed Telegram-signed fixtures.

Must not include:

- Frontend command center.
- Task submission/cancel/retry.
- Live Telegram API calls.

## PR 2: Read-Only Command Center APIs

Changes:

- Bootstrap endpoint.
- Task board read endpoint.
- Fleet/agent read endpoint.
- Sanitized task detail endpoint.

Must not include:

- Mutation endpoints.
- Rich message sending.
- Frontend action buttons.

## PR 3: Mini App Read-Only Shell

Changes:

- Telegram WebApp bootstrapping.
- Theme/safe-area support.
- Command center navigation.
- Read-only task board, fleet, agents, models, PR/CI, artifacts, settings, and safety gates.

Must not include:

- Backend auth changes beyond consuming PR 1.
- Task creation or cancel/retry/drain.

## PR 4: Command Composer And Task Submit

Changes:

- Composer UI.
- Backend `POST /api/factory/tasks`.
- Idempotency and envelope validation.
- Tests for sanitized owner task creation.

Must not include:

- Cancel/retry/drain.
- Deploy/restart/merge controls.

## PR 5: Safe Task Actions

Changes:

- Cancel and retry gates.
- Node drain gate.
- Confirmation and audit contracts.
- Tests proving denied roles cannot mutate state.

Must not include:

- Deployment, service restart, merge, or Telegram bot configuration mutation.

## PR 6: PR/CI/Artifacts

Changes:

- Sanitized artifact manifests.
- PR and CI read surfaces.
- Redacted report drawer.
- Role-gated raw log request flow.

Must not include:

- Artifact publishing.
- GitHub write actions.
- Raw unredacted logs.

## PR 7: Rich Message Adapter

Changes:

- Pure report model.
- Bot API 10.1 rich renderer.
- Plain text fallback.
- Tests against mocked Telegram client.

Must not include:

- Streaming drafts.
- Live capability probing against production bot.

## PR 8: Streaming

Changes:

- Factory event SSE/WebSocket stream.
- Mini App live updates.
- Optional `sendRichMessageDraft` behind feature flag.

Must not include:

- Guest Mode.
- Bot-to-Bot.
- Business mode.

## Future Policy PRs

Separate PRs required for:

- Guest Mode.
- Bot-to-Bot Communication.
- Business account integrations.
- Telegram Stars, gifts, paid media, subscriptions, invoices, or any money action.
- Managed bots.
