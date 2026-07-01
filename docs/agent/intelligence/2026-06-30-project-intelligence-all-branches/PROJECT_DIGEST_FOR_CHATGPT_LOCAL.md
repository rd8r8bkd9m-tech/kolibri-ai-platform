# Локальный digest для ChatGPT

Это локальное дополнение к task `2026-06-30-project-intelligence-all-branches`. Полный all-branches pack должен выполняться на сервере через Control Plane; на Mac выполнен только read-only обзор текущей рабочей копии.

## Что такое проект

Kolibri AI Platform / Kolibri Factory — собственная AI-платформа на mesh из серверов. Исторически README описывает 5 узлов: Home training/Redis, Main API+frontend, UIAP RAG, QJNS agent executor, 9FTS inference. Текущий код уже развивает это в factory-модель: Control Plane, Agent Host, Telegram owner gateway, mesh bridge, task leases, artifacts, review lifecycle.

Главный invariant: Mac должен быть thin client. Реальное сканирование веток, CI, сборки, training, deploy и git-операции должны идти server-side через Control Plane.

## Что есть в текущем локальном repo

- `backend/`: FastAPI gateway, `/api/chat`, `/ws/chat`, `/api/pipeline`, `/api/factory/status`, proxy на RAG/Agent/Inference, SQLite cache/history, TTS/STT/search, deterministic estimates, business docs and PDF.
- `frontend/`: React/Vite UI с chat, documents/search/cluster tabs, Kolibri bird, provider selector, WebSocket fallback.
- `ops/`: Control Plane sidecar, Agent Host, Telegram Gateway, Mesh Bridge, dispatch CLI, systemd units.
- `infra/network/`: nginx, legacy Kolibri Organism API, network config.
- `scripts/training/`: Qwen2.5-1.5B LoRA pipeline; FormulaLM как имя локально не оформлен.
- `tests/`: factory runtime, Telegram redaction, image generation, factory status, estimates/PDF.
- `.github/workflows/ci.yml`: compile, pytest, frontend build, validation, secret scan.
- `SERVER_INVENTORY_LOCAL.md`: локальная карта серверов/узлов из repo, без live-аудита.

## Текущий local git state

- Detached `HEAD`.
- Commit: `6d0317c52a9694448ee2c352dc196ce7a27b9487`.
- Subject: `Merge pull request #45 from rd8r8bkd9m-tech/codex/version-mesh-control-bridge`.
- После локальной документации dirty tree: `?? docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/`.
- Ветки `main`, `primary-candidate`, `qjns` локально не анализировались: нужен server pack.

## Самое важное по подсистемам

Servers: локально известны `home`, `main`, `uiap`, `qjns`, `9fts`, а также factory nodes `new`, `primary-candidate`, `home-live` и возможные `mesh-*`. Детальная live-карта должна быть собрана server-side: OS, uptime, services, ports, Control Plane heartbeat, Agent Host capabilities, repo state, artifacts/worktrees, health checks, blockers.

Control Plane: `ops/factory_control.py`. Redis-backed task/node state, `/v1/tasks`, `/v1/tasks/lease`, `/v1/nodes/register`, heartbeat, drain, retry/dead-letter, review task creation.

Agent Host: `ops/agent_host.py`. Server worker with node-local worktrees/artifacts. Умеет read-only probe, Telegram chat/image generation, implementation smoke tasks, retry-error patch task, PR review. Может делать git clone/checkout/commit/push только на server worker.

Telegram: `ops/telegram_gateway.py`. Owner-facing gateway, task intent routing, image intent routing, memory, human status, strict redaction of task/node/worktree/artifact/secret markers.

Mesh Bridge: `ops/mesh_control_bridge.py`. Bridges legacy mesh messages/nodes into Control Plane tasks/shadow nodes.

Estimates: `backend/estimate_engine.py`, `backend/document_engine.py`, `backend/pdf_engine.py`. Есть deterministic Decimal calculator, audit fingerprint, document pack and PDF tests. Денежные итоги должны оставаться только в deterministic calculator.

Frontend: `frontend/src/App.jsx`. Рабочий основной UI на React/Vite. Есть потенциально stale TSX компоненты с missing aliases/deps.

AI/LLM: `backend/providers.py` напрямую вызывает MiMo CLI. OpenAI используется в Agent Host image generation через env. Нужен LLM Gateway/provider abstraction.

Training: `scripts/training/` — Qwen LoRA, heavy deps; запускать только на server/training node.

DevOps: `scripts/deploy.sh` и README имеют legacy local/ssh workflow; нужно заменить на Control Plane server-only workflow.

## Главные риски

- В `infra/network/config.json` есть password-like secret field in tracked config; значение не повторять, проверить и ротировать.
- README/local deploy scripts противоречат thin-client invariant.
- `mimo run --dangerously-skip-permissions` встречается в legacy/provider paths.
- Control Plane auth boundary локально не очевиден.
- Hardcoded `10.99.0.x` endpoints разбросаны по backend/systemd/mesh.
- Frontend TSX component fragments могут ломать build, если попадут в import graph.
- FormulaLM как отдельный contract отсутствует; есть только Qwen LoRA training scripts.
- Полная branch truth неизвестна без server-side all-branches scan.
- Live state всех серверов неизвестен без server-side Control Plane inventory.

## Следующее правильное действие

1. Отправить server-side task из `HANDOFF_TO_CONTROL_PLANE.md`.
2. На сервере собрать полный intelligence pack по всем local/remote веткам и всем серверам.
3. Создать `SERVER_INVENTORY.md` и `servers/<node>.md` для каждого live node.
4. До merge/deploy проверить и убрать tracked secret-like config.
5. После intelligence pack обновить docs под server-only Control Plane workflow.

## Machine-readable summary

```yaml
project: Kolibri Factory
task_id: 2026-06-30-project-intelligence-all-branches
local_digest: true
full_all_branches_digest: false
execution_environment: mac_thin_client
current_branch: detached_HEAD
current_commit: 6d0317c52a9694448ee2c352dc196ce7a27b9487
dirty_tree:
  status: docs_only_after_local_intelligence
  paths:
    - docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/
subsystems:
  - backend_fastapi_gateway
  - frontend_react_vite
  - control_plane
  - agent_host
  - telegram_gateway
  - mesh_bridge
  - deterministic_estimates
  - document_pdf_generation
  - qwen_lora_training
  - devops_systemd_nginx_deploy
main_blockers:
  - full branch and CI state must be collected on server through Control Plane
  - tracked config contains password-like secret field requiring review/rotation
  - docs still describe local/ssh workflows that conflict with thin-client invariant
  - live state of all servers must be collected by server-side Control Plane task
next_tasks:
  - submit Control Plane intelligence task from HANDOFF_TO_CONTROL_PLANE.md
  - build SERVER_INVENTORY.md and servers/<node>.md for every live server/node
  - rotate/remove tracked secret-like config if real
  - write factory runtime architecture docs
  - reconcile README with server-only execution model
must_read_files:
  - docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/HANDOFF_TO_CONTROL_PLANE.md
  - docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/LOCAL_WORKTREE_INTELLIGENCE.md
  - docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/SERVER_INVENTORY_LOCAL.md
  - README.md
  - ops/factory_control.py
  - ops/agent_host.py
  - ops/telegram_gateway.py
  - ops/mesh_control_bridge.py
  - backend/main.py
  - backend/pipeline.py
  - backend/estimate_engine.py
  - frontend/src/App.jsx
  - .github/workflows/ci.yml
thin_client_invariant: true
server_execution_required: true
```
