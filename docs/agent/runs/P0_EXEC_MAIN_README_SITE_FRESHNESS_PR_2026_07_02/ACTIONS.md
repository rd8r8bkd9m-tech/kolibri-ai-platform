# Actions

- Confirmed the worktree was clean and based on `origin/main` at `f7ac32c`.
- Fetched `origin/main` before editing.
- Checked public route behavior:
  - `https://kolibriai.ru/?telegram=1` returned `200 text/html`.
  - `https://kolibriai.ru/api/factory/status` failed TLS hostname validation.
  - Forced `-k` access to `/api/factory/status` returned HTTP 400.
- Updated `README.md` to mark the July 1 release train as historical and record the current July 2 main status.
- Updated `frontend/src/App.jsx` so public site header/sidebar/welcome copy shows fresh nodes, total nodes, and online nodes separately.
- Updated `docs/agent/dispatcher/FACTORY_STATUS.md` with a 2026-07-02 freshness entry.
- Created required run artifacts in this directory.
