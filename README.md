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
| Home NOC | `ops/noc_control_center_server.py`, `ops/noc_wallboard.html` | Home NOC Control Center — fleet monitoring dashboard (port 9191). |
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

### Home NOC Control Center

| Endpoint | Description |
| --- | --- |
| `GET http://127.0.0.1:9191/` | NOC wallboard dashboard (standalone HTML). |
| `GET http://127.0.0.1:9191/api/snapshot` | Fleet snapshot: health, node/task counts by state. |
| `GET http://127.0.0.1:9191/api/health` | NOC server health check. |

> **Контроль:** порт 9191 — единственный порт NOC. Клиентский портал (8180) запрещён.

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
bash scripts/verify-home-noc.sh   # Home NOC verification
```

CI also validates tracked JSON/YAML files, scans for common secret patterns, and
blocks production secret-like paths in pull requests.

## Release Train

The active main-branch sync train for July 1, 2026 is recorded in
`docs/release/2026-07-01-main-readme-code-sync-release-train.md`.

Release rules for this train:

- Remote execution must happen on a server node, not on a Mac dispatcher.
- `main` must not be pushed directly.
- Pull requests must stay focused; do not mix unrelated product, docs, and
  operations changes in one PR.
- Owner approval is required before merge.
- PR #85 remains a release-gated item and must not be skipped.
