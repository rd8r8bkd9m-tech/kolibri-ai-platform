# Telegram Gateway Audit

Task id: P1_TELEGRAM_OWNER_GATEWAY_STABILIZATION_2026_07_02
Date: 2026-07-02
Scope: owner Telegram gateway stabilization only.
Status: artifact gate complete; docs-only follow-up on top of the runtime stabilization branch.

## Audited Surface

- `ops/telegram_gateway.py`
- `tests/test_telegram_gateway.py`
- `tests/test_agent_host_telegram_chat.py`
- Existing product contract docs under `docs/product/telegram-command-center/2026-07-01/`

The audited runtime is a private owner long-polling gateway that routes owner Telegram messages to the Factory Control Plane. It is not a public bot, Mini App implementation, webhook migration, deploy tool, credential tool, billing surface, model gateway, or Control Plane repair task.

## Current Owner-Facing Capabilities

- Owner allowlist check for private chats.
- Human Russian help text for `/start` and `/help`.
- `/task <objective>` submission into the Factory Control Plane.
- Plain-language chat handling through a remote owner chat task.
- Image generation task routing when the owner message is classified as an image request.
- `/status <task>` and `/cancel <task>` task lookups/actions through the Control Plane.
- `/retry <task>` task requeue through a copied envelope.
- `/nodes`, `/agents`, and `/queue` owner summaries.
- Task transition polling with owner-safe status messages.
- In-memory/persisted conversation context for follow-up questions.

## Completed Stabilization

- `/nodes`, `/agents`, and `/queue` now render compact owner summaries instead of raw records.
- Chat Control Plane submission failure now sends a redacted Russian owner message instead of leaking exception text.
- Focused fake Telegram/fake Control Plane tests cover summary redaction and failure redaction.
- Agent Host chat tests remain in the focused verification command.

## Redaction Expectations

Owner-visible Telegram replies must not include:

- Raw task IDs, node IDs, agent IDs, process IDs, queue item IDs, lease IDs, artifact IDs, or internal trace IDs.
- Absolute paths, worktree paths, result paths, log paths, command lines, env dumps, stderr, stack traces, or raw runner prompts.
- Tokens, keys, secrets, owner private data, credentials, webhook/poller state, or Telegram Bot API configuration details.
- Internal queue envelopes except as short human summaries.

Allowed owner-visible details:

- Human task status in Russian.
- Safe role names and high-level team availability.
- Safe counts, such as number of queued/running/completed/failed tasks.
- Safe preview or result URLs when already sanitized by the task result path.
- Clear fallback messages when Control Plane, runner, or report rendering fails.

## Guardrails Confirmed

- No live Telegram Bot API calls were required for the stabilization verification.
- No webhook mutation, poller state reset, service restart, deploy, credential rotation, or BotFather setting change is authorized by this run.
- No frontend/web/Mini App, billing, FormulaLM, model gateway, Control Plane P0, lease storm, PR #119, or PR #121 scope is included.
- Fake Telegram/fake Control Plane tests are the required validation mode for this gate.

## Residual Gaps

- `/status` and `/cancel` still depend on the shared task status formatter. Broader coverage for every possible Control Plane result payload remains useful.
- `/retry` was not part of the focused owner summary patch and should receive the same owner-safe review before any broader command-center rollout.
- Live canary is intentionally deferred until an owner-approved smoke window and explicit non-mutating command set exist.

