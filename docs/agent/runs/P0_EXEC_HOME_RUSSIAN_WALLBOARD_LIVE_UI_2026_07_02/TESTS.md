# TESTS

Passed:

```bash
.venv/bin/pytest -q tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py
```

Result: `6 passed in 0.16s`

Passed:

```bash
cd frontend
npx -y -p node@20 node node_modules/vite/bin/vite.js build
```

Result: Vite production build completed in `621ms`. It emitted the existing large chunk warning for a 506 kB JS asset.

Notes:

- Plain `npm run build` is blocked on this host because system Node is `18.19.1`, while Vite 8 requires Node `20.19+` or `22.12+`.
- A local `.venv`, `frontend/node_modules`, and `frontend/dist` were created for verification and are gitignored.
