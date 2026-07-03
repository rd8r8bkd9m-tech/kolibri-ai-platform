# Tests

## Commands Run

```bash
python3 -m py_compile backend/factory_status.py ops/factory_registry.py ops/factory_control.py ops/agent_host.py ops/kolibri-dispatch
/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py tests/test_factory_registry.py tests/test_factory_runtime.py tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py tests/test_factory_runtime_queue_contracts.py
```

## Result

- `py_compile`: passed.
- Targeted pytest: `41 passed`.
- GitHub Actions `Kolibri CI` passed for initial PR commit `86ae29f`; later pushed commits are awaiting/without reported workflow run at the time of this update.

## Network Registry Fix Suite

- Command: `/tmp/kolibri-p0-venv/bin/python -m py_compile ops/factory_registry.py ops/factory_control.py`
- Result: passed.
- Command: `/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_registry.py tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py`
- Result: 20 passed.

## Not Run

- Full repository pytest was not run in this sweep.
- Production service restart was not performed.
- GitHub CI was not checked from this branch yet.
- Draft PR push is working through the temporary write deploy key.
