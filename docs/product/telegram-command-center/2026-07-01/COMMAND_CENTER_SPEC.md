# Telegram Factory Command Center Spec

Task: `P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01`
Date: 2026-07-01
Scope: `@kolibriai_bot` and the `kolibriai.ru` Telegram Mini App.
Status: implementation-ready remote-only spec. This document does not authorize live bot mutation, deployment, service restart, or Bot API update consumption.

## Source Capability Map

Use the run artifact at `artifacts/P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01/capability-map.md` as the capability map for future implementation. It cites only official Telegram sources checked on 2026-07-01:

- Telegram Bot API: https://core.telegram.org/bots/api
- Telegram Mini Apps: https://core.telegram.org/bots/webapps
- Telegram Bot Features: https://core.telegram.org/bots/features

Key Telegram capabilities this spec relies on:

- Mini App launch surfaces: main Mini App/profile button, keyboard button, inline button, bot menu button, inline mode, direct link with `startapp`, and attachment menu.
- Mini App client APIs: `initData`, `initDataUnsafe`, theme params, safe area/content safe area, fullscreen, cloud storage, settings button, bottom/secondary buttons, QR/clipboard, file download, sharing, device and geolocation APIs.
- Server authentication: `initData` must be validated before use; `initDataUnsafe` is display-only until server verification succeeds.
- Bot API 10.1 Rich Messages: `sendRichMessage`, `sendRichMessageDraft`, `editMessageText.rich_message`, `Message.rich_message`, rich text, tables, details blocks, thinking blocks, media blocks, and inline/guest/Web App rich content.
- Bot API 10.0 Guest Mode and Bot-to-Bot Communication are future-gated only. They require loop prevention, rate limits, dedupe, bounded depth/time, and explicit policy review before activation.

## Product Objective

Build a Telegram-native command center where the owner can dispatch, monitor, review, and safely approve Kolibri Factory work from `@kolibriai_bot` and the `kolibriai.ru` Mini App. The command center must expose factory control without exposing secrets, internal paths, raw logs, private contacts, or irreversible actions.

The first production version should target one owner/operator flow:

1. Owner opens `@kolibriai_bot` or the Mini App.
2. Backend verifies Telegram identity and maps the user to a Kolibri role.
3. Owner composes a task, selects model/safety/PR options, and submits it to the Factory Control Plane.
4. The task board shows queued, leased/running, waiting review, review, completed, failed, cancelled, and dead-letter states.
5. The owner can inspect sanitized progress, artifacts, PR/CI state, and reviewer status.
6. Dangerous actions require explicit confirmation and audit records.

## Information Architecture

The Mini App first screen is the command center, not a landing page.

- Command composer: natural language objective, task kind, target repository/project, target node/capability, model/provider, priority, retry budget, review requirement, artifact expectations, safety gate summary, dry-run switch, and submit button.
- Task board: lanes for queued, running, waiting review, review, completed, failed, cancelled, and dead-letter. Each card shows human title, sanitized status, assignee role/name, age, branch/PR if any, CI/review chips, and next safe action.
- Fleet: node health, capabilities, active task, drain status, CPU/RAM/disk, heartbeat freshness, and role card names already used by Kolibri (`Директор`, `Инженер`, `Ревьюер`, etc.).
- Agents: agent id, node id, pid, runner, supported task kinds, current lease, last heartbeat, and last sanitized result.
- Models: active chat model/provider, available providers, model health/stats, cost/rate warning, and per-task model override.
- PR/CI: branch, PR URL, review task, check runs, failure summaries, and merge readiness. No merge/deploy action in the first PR.
- Artifacts: sanitized result manifest, downloadable safe artifacts, redacted logs, screenshots, generated images, and source task links.
- Settings: owner identity, roles, session status, notification preferences, theme, command defaults, safe display mode, and redaction preview.
- Safety gates: destructive operations, live bot mutation, deployment/restart, external messaging, money/Stars/gifts, secret access, broad data export, and Guest/Bot-to-Bot/Business features.

## Owner Auth Policy

Telegram Mini App auth must be server-side and short-lived.

- Verify `Telegram.WebApp.initData` on the backend before creating any Kolibri session. Reject missing, malformed, stale, replayed, or signature-invalid init data.
- Never trust `initDataUnsafe` for authorization or role mapping. It can be used only after verified `initData` establishes the same Telegram user.
- Use an allowlist from configuration for initial owner Telegram user IDs. Store only non-secret identifiers and redacted display metadata in session records.
- Map Telegram users to Kolibri roles: `owner`, `operator`, `reviewer`, `observer`, and `guest_candidate`. `owner` can submit and approve gated actions; `operator` can submit bounded tasks; `reviewer` can inspect and review; `observer` is read-only; `guest_candidate` has no factory access until elevated.
- Issue short-lived backend sessions after initData verification. Recommended TTL: 15 minutes idle, 8 hours absolute max, refresh only with fresh verified initData or approved Telegram Login/OIDC flow.
- Telegram Login/OIDC can be added for non-Mini-App web access, but it must use the same role mapping, TTL, replay checks, and audit log.
- Redact secrets before persistence and response rendering. Redaction must cover bot tokens, API keys, JWT secrets, private IP/path details when not explicitly requested, env values, SSH destinations, and raw owner prompts in failure payloads.

## Backend Contracts

Add these contracts in future PRs, without changing existing runtime behavior in the spec PR:

- `POST /api/telegram/auth/session`: validates Mini App `initData`, returns short-lived session and role claims.
- `GET /api/factory/command-center/bootstrap`: returns role, feature flags, redaction policy, factory status, task counts, and supported actions.
- `POST /api/factory/tasks`: submits owner task envelopes to the Control Plane with idempotency.
- `GET /api/factory/tasks`: returns sanitized task board data.
- `GET /api/factory/tasks/{task_id}`: returns task detail, timeline, redacted result, PR/CI links, and artifact manifest.
- `POST /api/factory/tasks/{task_id}/cancel`: owner/operator gated cancel.
- `POST /api/factory/tasks/{task_id}/retry`: owner/operator gated retry with new idempotency key.
- `POST /api/factory/nodes/{node_id}/drain`: owner-only, confirmation required.
- `GET /api/factory/artifacts/{task_id}`: lists safe artifacts; raw logs require owner role and redaction.
- `GET /api/factory/events`: SSE/WebSocket stream for task/fleet changes.

Existing files to read first before implementation:

- `ops/telegram_gateway.py`: current owner allowlist, long-polling gateway, command handling, task/chat/image envelopes, status formatting, secret/path redaction, and task transition polling.
- `ops/factory_control.py`: Redis-backed task, node, lease, retry, cancel, complete, annotate, and drain control-plane contracts.
- `ops/agent_host.py`: task execution, artifact manifest writing, result schemas, supported task kinds, PR review path, and Telegram chat/image task handling.
- `backend/factory_status.py`: normalized factory status model used by the frontend.
- `backend/main.py`: FastAPI app, current `/api/factory/status`, chat websocket, provider/model endpoints, and proxy routing.
- `frontend/src/App.jsx`: current chat/doc/search/fleet UI and factory status rendering.
- `ops/orchestrator_roster.py`: Russian display names and role cards for fleet/agent views.
- `tests/test_telegram_gateway.py`, `tests/test_factory_runtime.py`, `tests/test_factory_runtime_contracts.py`, `tests/test_factory_status.py`: existing contracts to extend.

## Rich And Streaming Messages

Bot chat and Mini App rendering should share a structured progress model.

- Use Bot API 10.1 rich messages where available for task reports: heading, status table, reviewer block, artifact list, PR/CI links, and collapsible details.
- Use `sendRichMessageDraft` for partial progress when Telegram client support and bot capability checks pass.
- Use `editMessageText` with `rich_message` for stable status cards.
- Use rich details blocks for logs, test summaries, and reviewer notes; default collapsed.
- Use rich thinking/progress blocks only for sanitized task progress, not private chain-of-thought.
- Fallback path: plain `sendMessage`/`editMessageText` with compact text under current length limits, no markdown dependency, and no leaked internal metadata.
- The Mini App should stream task events via SSE/WebSocket and render the same normalized event objects as cards, timelines, and report drawers.

## Safety Gates

The command center must never perform these actions without an explicit owner confirmation in the same session:

- Deploy/restart services, mutate live Telegram bot settings, change webhooks, modify BotFather-level settings, rotate tokens, drain nodes, cancel active tasks, retry with side effects, merge PRs, publish artifacts externally, or contact external users.
- Money actions, including Telegram Stars, subscriptions, gifts, paid media, invoices, and any purchase/transfer flow.
- Business account actions, Guest Mode replies, or Bot-to-Bot messaging.

Hard blocks for the initial implementation:

- Do not call `getUpdates`, `setWebhook`, `deleteWebhook`, `setMyCommands`, or `setChatMenuButton` from CI, tests, docs generation, or Mini App backend startup.
- Do not consume live updates in tests. Mock all Telegram API calls.
- Do not mutate production service files or systemd units in the Mini App implementation PR.

## Business, Guest, And Bot-To-Bot Policy

Business accounts, Guest Mode, and Bot-to-Bot Communication are future-gated features.

- Default state: disabled in backend feature flags and hidden in the Mini App.
- Activation requires a separate policy PR, threat model, rate limiting, dedupe, bounded interaction depth, per-chat and global quotas, and operator-visible audit logs.
- Guest Mode must not leak external contact details, chat history, participant lists, owner project details, or private artifacts.
- Bot-to-Bot must include loop storm prevention: message dedupe, reply cooldown, max depth, max duration, max spend, and kill switch.
- Business mode must prevent spam, ToS abuse, external contact leakage, and unsupervised customer/user outreach.
- Money actions remain disabled unless a separate owner-approved payments policy exists.

## PR-Sized Implementation Slices

Future work must be split into small PRs:

1. Auth contract PR: backend initData verifier, session model, role mapping, tests. Do not include frontend UI or task mutation.
2. Command-center read model PR: backend bootstrap/task/fleet read APIs using existing control plane. Do not include task submission or Telegram Bot API changes.
3. Mini App shell PR: responsive Mini App shell, Telegram theme/safe area integration, read-only task board/fleet. Do not include auth policy changes beyond consuming the session API.
4. Task composer PR: submit owner task envelopes through the backend to the control plane with idempotency and tests. Do not include cancel/retry/drain.
5. Task action PR: cancel/retry/drain gates with confirmation, audit records, and tests. Do not include deploy/merge/live bot mutation.
6. PR/CI/artifacts PR: sanitized artifact manifest, PR/CI read surfaces, redacted report drawer. Do not include artifact publishing or raw log export.
7. Rich message adapter PR: capability-gated rich report renderer plus plain text fallback. Do not include `sendRichMessageDraft` streaming yet.
8. Streaming PR: normalized event stream for Mini App and rich draft progress in the bot. Do not include Guest/Bot-to-Bot/Business support.
9. Policy-gated future PRs: Guest Mode, Bot-to-Bot, Business, Stars/payments, and managed bots each require separate specs and reviews.

Changes that must not be mixed in one PR:

- Auth/session logic with UI layout changes.
- Backend task mutation with frontend board rendering.
- Telegram Bot API mutation methods with Mini App read-only features.
- Rich message adapter with control-plane lease/retry changes.
- Deploy/restart/systemd changes with product feature work.
- Payment/Business/Guest/Bot-to-Bot policy with normal command-center work.
