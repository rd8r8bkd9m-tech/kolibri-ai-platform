# Actions

Implemented:
- Audited `frontend/src/App.jsx`, `frontend/src/App.css`, `backend/main.py`, `backend/factory_status.py`, `backend/routes_v1.py`, and existing route tests.
- Checked `kolibriai.ru` in Yandex Browser with Computer Use.
- Checked public HTTP behavior with `curl`.
- Fetched remote branches and reviewed frontend artifacts from:
  - `origin/agent/KOL-FE-V3-SHELL-CONTRACT-20260625-001/primary/canvas-shell`
  - `origin/codex/public-proxy-chat-contract`
  - `origin/agent/TG-20260626080929-4297-kolibriairu/impl/kolibriairu`
- Applied the best safe artifacts:
  - production-like welcome copy and action shape from FE V3/current `kolibriai.ru`
  - same-origin websocket/API contract already present on main
  - ESLint flat config from remote frontend branches
- Updated `frontend/src/App.jsx` with:
  - `kolibriai.ru` product-domain cue
  - "Чем могу помочь?" first screen
  - honest factory/provider/knowledge fallback statuses
  - guarded document upload/list behavior
  - `/api/knowledge/search` instead of direct `/rag/search`
- Updated `frontend/src/App.css` with:
  - production-like welcome styling
  - status pills and service banners
  - quieter background treatment
  - removal of an obsolete broken CSS comment block
- Updated `tests/test_factory_status.py` with route and product-copy assertions.

Not done by design:
- No backend route repair.
- No deployment or server credential work.
- No Telegram, billing, FormulaLM, Control Plane, model gateway, or PR #46 changes.

