# Tests

Verified during mesh07 and re-run during mesh11 salvage:

```bash
python3 -m pytest -q tests/test_factory_runtime.py
```

Result during mesh11 salvage: `9 passed in 0.10s`.

```bash
python3 -m py_compile ops/factory_control.py ops/agent_host.py backend/factory_status.py
```

Result during mesh11 salvage: passed.

```bash
python3 -m pytest -q tests/test_factory_runtime.py tests/test_prompt3_fabric_api_surface.py tests/test_fabric_control.py
```

Result during mesh11 salvage: `20 passed in 0.15s`.

```bash
python3 -m pytest -q tests/test_factory_status.py
```

Result during mesh11 salvage: blocked at collection because `httpx` is not installed in this environment (`ModuleNotFoundError: No module named 'httpx'`).

