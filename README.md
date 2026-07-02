# Kolibri AI Platform

Kolibri AI Platform is the control, chat, and factory automation surface for the
Kolibri server fleet. The current main branch contains a FastAPI backend, React
frontend, Redis-backed factory control-plane sidecars, Telegram/factory
orchestration utilities, deployment scripts, and regression tests for the active
runtime contracts.

This repository is operated through protected release trains. Do not push
directly to `main`. Product, documentation, and factory-runtime changes should
land through focused pull requests with CI evidence and owner approval.

## Current Components

| Area | Path | Purpose |
| --- | --- | --- |
| Backend API | `backend/` | FastAPI chat, provider catalog, conversations, TTS/STT, web search, pipeline, and factory status endpoints. |
| Frontend | `frontend/` | React 19 and Vite application for the Kolibri chat and factory status UI. |
| Factory control | `ops/factory_control.py`, `ops/agent_host.py` | Redis-backed task queue, leases, node heartbeat, review tasks, and agent execution contracts. |
| Telegram gateway | `ops/telegram_gateway.py` | Owner-facing Telegram command and chat integration for factory workflows. |
| Mesh bridge | `ops/mesh_control_bridge.py` | Local control bridge for mesh/factory node operations. |
| Deployment | `scripts/deploy.sh`, `ops/systemd/` | Server deployment and systemd service units. |
| Tests | `tests/`, `backend/tests/`, `frontend/tests/` | Python contract tests and frontend layout guards. |

## Backend API

The backend entry point is `backend/main.py`. Current local routes include:

| Endpoint | Description |
| --- | --- |
| `GET /api/health` | Backend health and provider status. |
| `GET /api/providers` | Configured AI provider status. |
| `GET /api/models` | Model catalog and active system prompt. |
| `POST /api/chat` | Cached chat generation through the provider manager. |
| `WS /ws/chat` | Streaming-style websocket chat exchange. |
| `POST /api/conversations` | Create a stored conversation. |
| `GET /api/conversations` | List stored conversations. |
| `GET /api/conversations/{conv_id}/messages` | Read stored conversation messages. |
| `DELETE /api/conversations/{conv_id}` | Delete a stored conversation. |
| `POST /api/tts` | Text-to-speech generation. |
| `GET /api/tts/voices` | TTS voice catalog. |
| `POST /api/search` | Web search helper. |
| `POST /api/tools` | Tool-call helper endpoint. |
| `POST /api/pipeline` | Unified pipeline execution. |
| `GET /api/pipeline/health` | Pipeline dependency health. |
| `GET /api/factory/status` | Live factory status normalized for the frontend. |
| `GET /cluster/status` | Legacy cluster status compatibility endpoint. |

The versioned router in `backend/routes_v1.py` is also included by the backend
for `/v1` contracts.

### Fabric Control API

| Endpoint | Описание |
| --- | --- |
| `GET /v1/fabric/health` | Health защищенного Fabric API |
| `GET /v1/fabric/policy` | Owner rights, auth/authz/scope/logging/rotation policy |
| `GET /v1/fabric/routes` | Представление всех серверов через API или fallback relay |
| `POST /v1/fabric/route` | Direct route или structured blocked status |
| `POST /v1/fabric/relay` | Safe relay contract |
| `POST /v1/fabric/bootstrap` | Контракт bootstrap нового сервера без вывода секретов |
| `GET /v1/fabric/keys/rotation` | Node identity и key rotation policy |

## Quick Start

Backend:

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Factory control sidecar:

Основной путь управления фабрикой — защищенный Fabric API control plane. SSH не является control plane и допускается только для bootstrap, emergency recovery и диагностики, когда API недоступен или еще не установлен. Контракт API-first управления описан в [docs/fabric-api-first-control.md](docs/fabric-api-first-control.md).

```bash
python3 ops/factory_control.py --host 127.0.0.1 --port 8765
```

## Verification

Run the same categories that CI covers before opening or updating a PR:

```bash
python3 -m compileall -q backend ops scripts
python3 -m pytest -q
cd frontend && npm install && npm run build
```

CI also validates tracked JSON/YAML files, scans for common secret patterns, and
blocks production secret-like paths in pull requests.

## Current Main Status

Freshness snapshot: 2026-07-02.

Current `main` includes the July 2 factory-control repair sequence through
`f7ac32c` (`docs: dispatch factory control deploy canary (#104)`). The earlier
July 1 README release train is preserved as historical evidence in
`docs/release/2026-07-01-main-readme-code-sync-release-train.md`; it is no
longer the active public status.

Recently merged public/runtime work now present on `main`:

- API-first Fabric contracts and Prompt #3 surface from PR #85.
- Telegram Superfactory bot and Mini App command layer from PR #89.
- MIMO runner output/auth classification from PR #91.
- Factory node heartbeat freshness classification from PR #97.
- July 2 post-merge canary, rollback, import-path repair, and deploy-canary
  documentation through PRs #100-#104.

Owner-facing freshness rules:

- `GET /api/factory/status` is the public factory-status contract consumed by
  the site.
- Fresh heartbeat capacity must be shown separately from degraded/stale cards.
- The owner server set is 20 canonical servers; Control Plane may expose more
  node cards because mesh, duplicate, stale, and metadata cards are still
  visible for auditability.
- Public status claims must cite a current rendered/API check or record the
  exact blocker instead of carrying stale release-train language forward.

Current release rules:

- `main` must not be pushed directly.
- Pull requests must stay focused; do not mix unrelated product, docs, and
  operations changes in one PR.
- Remote execution should happen on server nodes for runtime/product changes;
  local thin-client work is limited to dispatch, docs relays, and scoped PR
  edits when the task explicitly asks for a PR.
- Owner approval is required before merge.
