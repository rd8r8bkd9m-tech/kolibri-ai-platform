# Telegram Factory Runtime Gap Audit

Task: `P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01`
Date: 2026-07-01
Scope: docs-only audit for `@kolibriai_bot` and `kolibriai.ru` Telegram Mini App.

## Current Runtime Summary

The current repository already has a remote factory foundation:

- `ops/telegram_gateway.py` is a Telegram long-polling owner gateway. It authorizes only configured owner IDs in private chats, classifies text into chat/task/image intents, creates factory task envelopes, watches task transitions, formats owner-safe messages, and filters internal metadata.
- `ops/factory_control.py` is a minimal Redis-backed control plane with node registration, heartbeat, drain, task creation, lease, heartbeat, completion, annotation, failure, retry, cancel, and read APIs.
- `ops/agent_host.py` executes leased tasks, writes result artifacts and manifests, supports Telegram chat/image tasks, owner remote work, PR review tasks, and read-only probes.
- `backend/main.py` exposes the app API, `/api/factory/status`, chat endpoints, provider/model endpoints, and static frontend serving.
- `backend/factory_status.py` normalizes control-plane health, nodes, tasks, queue size, RAM/CPU/disk, and Russian role names for frontend consumption.
- `frontend/src/App.jsx` currently implements a web chat UI, documents/search views, and a fleet/status view backed by `/api/factory/status`.

## Confirmed Gaps

### Telegram Mini App Auth

Gap: there is no server-side Telegram Mini App `initData` verification or session endpoint.

Read first:

- `backend/main.py`
- `ops/telegram_gateway.py`
- `tests/test_telegram_gateway.py`

Implementation target:

- Add a backend verifier for Mini App `initData`.
- Add short-lived session issuance and role mapping.
- Keep current owner-id allowlist behavior for the bot until a tested migration exists.

### Command Center Backend

Gap: only `/api/factory/status` exists for read-only fleet status. There are no command-center read models for tasks, artifacts, PR/CI, or agent details, and no backend task submission API for the Mini App.

Read first:

- `backend/factory_status.py`
- `backend/main.py`
- `ops/factory_control.py`
- `ops/kolibri-dispatch`
- `tests/test_factory_status.py`
- `tests/test_factory_runtime_contracts.py`

Implementation target:

- Add session-protected read APIs first.
- Add mutation APIs only after auth and audit gates exist.
- Preserve the Redis control-plane envelope shape.

### Mini App UX

Gap: the frontend is a general Kolibri AI web app, not a Telegram Mini App command center. It lacks Telegram WebApp bootstrapping, safe area handling from Telegram APIs, command composer, task board lanes, agent/model/PR/CI/artifact surfaces, and safety gate screens.

Read first:

- `frontend/src/App.jsx`
- `frontend/src/App.css`
- `frontend/src/components/MessageBubble.tsx`
- `frontend/package.json`
- `frontend/tests/mobile_layout_guard.mjs`

Implementation target:

- Build a Mini App shell that consumes Telegram theme/safe-area data.
- Add read-only command-center views before adding write actions.
- Keep existing web app behavior unless a PR explicitly migrates it.

### Rich/Streaming Bot Reports

Gap: the gateway uses `sendMessage`, `sendPhoto`, and `editMessageText` plain text/image calls. It does not support Bot API 10.1 rich messages or draft streaming.

Read first:

- `ops/telegram_gateway.py`
- `tests/test_telegram_gateway.py`
- `ops/agent_host.py`

Implementation target:

- Add an internal report model independent of Telegram rendering.
- Add a rich renderer behind feature flags.
- Keep plain text fallback as the default until compatibility is proven.

### PR/CI And Artifacts

Gap: agent results can include PR URLs and artifact manifests, but the backend/frontend do not present a unified PR/CI/artifact read model.

Read first:

- `ops/agent_host.py`
- `ops/factory_control.py`
- `tests/test_agent_host_telegram_chat.py`
- `tests/test_agent_host_image_generation.py`

Implementation target:

- Standardize sanitized artifact manifests for task detail views.
- Add PR/CI read models without merge/deploy actions.
- Expose raw logs only after role check and redaction.

### Safety And Policy

Gap: current bot has owner-only chat safeguards, but there is no Mini App safety gate framework for destructive actions, live bot mutation, external contact restrictions, payments, Guest Mode, Business mode, or Bot-to-Bot loop prevention.

Read first:

- `ops/telegram_gateway.py`
- `ops/orchestrator_memory.py`
- `tests/test_telegram_gateway.py`

Implementation target:

- Add explicit feature flags and confirmation contracts.
- Keep Guest Mode, Business mode, Bot-to-Bot, and money actions disabled.
- Add tests proving forbidden actions cannot be triggered accidentally.

## Implementation Risks

- Live Telegram mutation risk: accidental use of update-consuming or bot-configuration methods during tests or startup. Mitigation: mock Bot API, denylist live methods in tests, and keep this audit PR docs-only.
- Secret leakage risk: raw task results can include paths, tokens, owner prompts, or environment names. Mitigation: central redaction layer before persistence and rendering.
- Control-plane coupling risk: Mini App APIs could duplicate or bypass `ops/factory_control.py`. Mitigation: backend adapts existing control-plane contracts instead of inventing a parallel queue.
- UI overreach risk: command center could mix read model, auth, task mutation, and rich messaging in one large PR. Mitigation: use the PR slice plan in the run artifacts.
- Loop/spam risk: future Guest/Bot-to-Bot/Business features can amplify messages. Mitigation: future-gated by default and separate policy PR required.
