# Tests

Remote reported successful checks:

```bash
python3 -m pytest -q tests/test_factory_runtime.py tests/test_telegram_gateway.py
# 37 passed

# In temp venv with backend/requirements.txt:
python -m pytest -q
# 63 passed

npm --prefix frontend run test:mobile-layout
# passed

# Node 22 frontend build via Vite
# passed

git diff --check
# passed

python3 -m compileall -q ops backend tests
# passed
```

Failing wrapper/verifier command:

```bash
python3 -m pytest -q tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py
```

Failure classification:

- `tests/test_factory_status.py` and `backend/tests/test_factory_status_fast_health.py` failed collection in the system environment because `httpx` was missing.
- This is an environment/verifier issue, because the remote review also reported a temp venv run with `backend/requirements.txt` where the suite passed.

Command-node GitHub evidence:

- PR #97 head: `f542c5c7e828091c2bf762f5ce24a30953dc0906`.
- GitHub check `ci`: completed, success.
- Mergeable: `true`.
- Mergeable state: `clean`.
