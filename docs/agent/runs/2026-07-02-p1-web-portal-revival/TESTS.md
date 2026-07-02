# Tests

Passed:
- `npm --prefix frontend run build`
  - Result: pass.
  - Note: Vite reports a pre-existing large chunk warning around `506 kB`.
- `npm --prefix frontend run lint`
  - Result: pass after adding `frontend/eslint.config.js`.
- `npm --prefix frontend run test:mobile-layout`
  - Result: pass.
- `/tmp/kolibri-p1-web-py312/bin/python -m pytest -q tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py`
  - Result: `5 passed`.
- Yandex Browser local visual check:
  - Opened `http://127.0.0.1:5174/`.
  - Result: portal rendered, first screen visible, fallback statuses visible, no white screen.

Environment notes:
- Initial frontend build/lint failed before `npm install` because `vite` and `eslint` were not installed in the clean worktree.
- Initial pytest with system Python 3.14 failed because backend dependencies pull `pydantic-core` that does not build cleanly against Python 3.14/PyO3 in this environment.
- Retried targeted tests with Python 3.12 and only required packages; tests passed.

