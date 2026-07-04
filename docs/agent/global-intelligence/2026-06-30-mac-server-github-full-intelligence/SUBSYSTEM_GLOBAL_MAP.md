# Subsystem global map

## Backend/API

- paths: `backend/`, `backend/routes_v1.py`, `backend/adapter.py`, `backend/providers.py`.
- risk: provider stack and API contracts are touched by runtime dirty changes on `primary-candidate`.

## Estimates/documents/PDF

- paths: `backend/estimate_engine.py`, `backend/document_engine.py`, `backend/pdf_engine.py`, `backend/tests/test_estimate_document_pdf_engines.py`.
- branch context: deterministic estimates are in PR #46.

## Frontend/PWA

- path: `frontend/`.
- runtime: `kolibri-frontend-dev` active on `main`.
- branch context: large PWA refactor in PR #46.

## Control Plane

- path: `ops/factory_control.py`.
- runtime: active on `main`, standby/control on `primary-candidate`.
- risks: queue truncation, artifact path drift, stale task/index problems.

## Agent Host

- path: `ops/agent_host.py`.
- runtime: active on multiple nodes.
- risks: generic runner contract must be hardened before more important remote tasks.

## Mesh/control bridge

- path: `ops/mesh_control_bridge.py`.
- runtime: active on `main`.
- risk: server runtime dirty modifications.

## Telegram reports/chat

- paths: `ops/telegram_gateway.py`, `ops/agent_host.py`.
- PRs: #61, #81 and many historical `agent/TG-*` branches.

## Billing

- current baseline: not a complete standalone subsystem in `main`.
- branch context: T-Bank billing scaffold in PR #46.
- risk: mixed with unrelated PWA/autonomy/FormulaLM work.

## FormulaLM/training

- paths: `scripts/training/`, backend provider/benchmark hooks.
- branches: `codex/formulalm-rd-integration-20260629`, PR #74.
- risk: local Mac benchmark should remain blocked; server remote-only guard not fully enforceable yet.

## AI/LLM provider stack

- paths: `backend/providers.py`, `backend/adapter.py`.
- providers/context: OpenAI-compatible, Kimi, MiMo/Mimo, Yandex, Google/Gemini, Ollama, vLLM, LiteLLM, MCP, RAG, embeddings, image generation.
- risk: provider changes are spread across branches and runtime dirty files.

## DevOps/bootstrap

- paths: `ops/systemd/`, `ops/install-telegram-secret.sh`, `ops/kolibri-dispatch`, `infra/`.
- risk: do not print secret files/env values; separate credential fixes from product code.

## GitHub/CI

- path: `.github/workflows/ci.yml`.
- workflow: `Kolibri CI`.
- risks: one recent failed run; branch protection API limitations; server auth failures.
