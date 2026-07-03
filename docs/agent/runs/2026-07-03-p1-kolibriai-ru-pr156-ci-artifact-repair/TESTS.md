# Tests

## GitHub Actions Failure Source

- `Kolibri CI` run `28654923623`: failed before repair.
- Failed test: `tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint`.

## Local Verification

```text
.venv/bin/python -m pytest tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint -q
```

Result: passed, `1 passed`.

```text
.venv/bin/python -m pytest -q
```

Result: passed, `131 passed, 1 warning`.

```text
python3 -m compileall -q backend infra scripts
```

Result: passed.

```text
PATH=/var/lib/kolibri-agent/tools/node20/node_modules/node/bin:$PATH npm install --package-lock=false
```

Working directory: `frontend`

Result: passed.

```text
PATH=/var/lib/kolibri-agent/tools/node20/node_modules/node/bin:$PATH npm run build
```

Working directory: `frontend`

Result: passed.

```text
PATH=/var/lib/kolibri-agent/tools/node20/node_modules/node/bin:$PATH npm run lint
```

Working directory: `frontend`

Result: passed.

```text
PATH=/var/lib/kolibri-agent/tools/node20/node_modules/node/bin:$PATH npm run test:mobile-layout
```

Working directory: `frontend`

Result: passed, `mobile layout guard passed`.

```text
git diff --check
```

Result: passed.

## Notes

- The branch-head pytest collection has 19 Python test files and passed locally.
- The prior GitHub pull-request merge ref had one additional main-side Python test file and failed only on `tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint`; that contract is now fixed on the branch.
