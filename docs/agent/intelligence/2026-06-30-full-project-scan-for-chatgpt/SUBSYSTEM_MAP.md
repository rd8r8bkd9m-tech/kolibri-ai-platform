# Subsystem Map

## Backend API

- `backend/main.py`: FastAPI app, chat, websocket, conversations, TTS/STT/search/tools, pipeline, factory status, cluster proxy.
- `backend/pipeline.py`: intent detection and RAG/agent/inference chains.
- `backend/factory_status.py`: Control Plane status normalization for frontend.
- `backend/routes_v1.py`, `backend/adapter.py`: v1 compatibility/API surface.

## Estimator/Documents

- `backend/estimate_engine.py`: deterministic estimates.
- `backend/document_engine.py`: document pack creation.
- `backend/pdf_engine.py`: Cyrillic PDF output.

## Frontend/PWA

- `frontend/src/App.jsx`: primary React app shell.
- `frontend/src/App.css`, `frontend/src/globals.css`: visual system.
- `frontend/src/components/*`: avatar, bird animation, message/document bubble, thinking indicator.
- `frontend/tests/mobile_layout_guard.mjs`: CSS guard.

## Factory Control Plane

- `ops/factory_control.py`: Redis-backed task and node sidecar.
- `ops/agent_host.py`: persistent executor/lease runner.
- `ops/kolibri-dispatch`: operator CLI.
- `ops/systemd/*`: services.

## Telegram/Mesh

- `ops/telegram_gateway.py`: Telegram owner interface and task submission.
- `ops/mesh_control_bridge.py`: mesh-to-Control Plane bridge.
- `ops/orchestrator_memory.py`: conversational memory.
- `ops/orchestrator_roster.py`: human-readable node cards.

## Network/Organism

- `infra/network/api.py`, `infra/network/organism.py`: Redis/job/state/node APIs; likely duplicated implementations.
- `infra/network/nginx.conf`, `infra/network/config.json`: network config artifacts.

## Training

- `scripts/training/*`: dataset prep, generation, fine-tuning and adapter merge scripts.

