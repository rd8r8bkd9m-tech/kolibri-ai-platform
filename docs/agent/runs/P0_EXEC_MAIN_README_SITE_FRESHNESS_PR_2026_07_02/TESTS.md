# Tests

Verification results:

- `git diff --check`: passed.
- `python3 -m compileall -q backend ops scripts`: passed.
- `python3 -m pytest -q`: blocked on the system interpreter because `pydantic`
  and `httpx` are not installed there.
- `python3 -m venv .venv`: passed; `.venv/` is ignored by repo `.gitignore`.
- `.venv/bin/python -m pip install -r backend/requirements.txt pytest==7.4.4`:
  passed.
- `.venv/bin/python -m pytest -q`: `131 passed, 1 warning in 41.39s`.
- `npm --prefix frontend install`: passed with Node engine warnings because
  this node has Node `v18.19.1` while Vite/eslint packages require Node
  `20.19+` or `22.12+`.
- `npm --prefix frontend run test:mobile-layout`: `mobile layout guard passed`.
- `npm --prefix frontend run build`: blocked by `node_runtime_too_old`; Vite
  reported Node `20.19+` or `22.12+` is required and failed under Node
  `v18.19.1` with `ReferenceError: CustomEvent is not defined`.
- `curl -fsSI --max-time 10 https://kolibriai.ru/?telegram=1`: blocked by TLS
  hostname mismatch.
- `curl -kfsSI --max-time 10 https://kolibriai.ru/?telegram=1`: returned
  `200 OK`, `Content-Type: text/html`.
- `curl -fsS --max-time 10 https://kolibriai.ru/api/factory/status`: blocked by
  TLS hostname mismatch.
- `curl -kfsS --max-time 10 https://kolibriai.ru/api/factory/status`: returned
  HTTP 400.

No secrets were printed.
