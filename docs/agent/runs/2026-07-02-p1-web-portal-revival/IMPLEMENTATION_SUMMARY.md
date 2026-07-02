# Implementation Summary

Files changed:
- `frontend/src/App.jsx`
- `frontend/src/App.css`
- `frontend/eslint.config.js`
- `tests/test_factory_status.py`

Frontend changes:
- Added normalized provider handling and visible provider errors.
- Added factory fallback status for `/api/factory/status` failures.
- Added knowledge availability state.
- Guarded documents and upload when `/api/knowledge` is down.
- Changed search to `/api/knowledge/search`.
- Added product-domain first screen aligned to `kolibriai.ru`.
- Added route/status service banners.
- Preserved same-origin production API behavior.

Test/config changes:
- Added ESLint flat config from existing remote frontend branches so `npm run lint` works under ESLint 10.
- Extended route/status tests to assert:
  - `/api/factory/status`
  - `/api/knowledge/search`
  - no direct `${API_BASE}/rag/search`
  - `kolibriai.ru`
  - "Чем могу помочь?"
  - "суверенная AI-фабрика"

Backend:
- No backend files changed.

