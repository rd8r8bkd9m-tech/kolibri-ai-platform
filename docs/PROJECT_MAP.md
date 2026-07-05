# Project Map

## Active Runtime

- `backend/` — FastAPI backend, routes, provider catalog, conversations, TTS/STT, search, pipeline, factory status.
- `frontend/` — React/Vite frontend and GitHub Pages build output.
- `ops/factory_control.py` — Redis-backed factory control plane sidecar.
- `ops/agent_host.py` — agent host contract and execution adapter.
- `ops/telegram_gateway.py` — Telegram owner-facing gateway.
- `ops/telegram_superfactory.py` — Telegram Mini App and runner policy contracts.
- `ops/mesh_control_bridge.py` — mesh/factory node bridge.

## Docs and Release

- `docs/fabric-api-first-control.md` — API-first control doctrine.
- `docs/telegram-superfactory.md` — Telegram Superfactory docs.
- `docs/superfactory/` — strategy and bootstrap reference.
- `docs/agent/` — dispatcher and run evidence.
- `docs/release/` — release train docs.
- `release/` — DNS instructions and branch release files.

## Generated / Local

- `.codex/`, `.codex-runtime/`, `.factory/`, `.mimocode/` — local/runtime agent material.
- `logs/`, `output/`, `server.pid` — local runtime outputs.
- `frontend/storybook-static/`, `frontend/test-results/` — generated frontend artifacts.
- `node_modules/`, `.venv/`, `backend/venv/`, `__pycache__/` — dependencies/cache.

## Related Foundation

Rust-first Calibri V1 foundation exists in a separate worktree:

```text
/Users/kolibri/.codex/worktrees/b56d/kolibri-ai-platform
```

Do not copy or merge it into this branch without a focused plan.
