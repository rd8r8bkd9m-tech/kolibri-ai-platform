# TESTS

Passed:

```bash
python3 -m pytest tests/test_factory_runtime_queue_contracts.py tests/test_factory_runtime.py tests/test_prompt3_fabric_api_surface.py
```

Result: `20 passed in 0.19s`

Passed:

```bash
bash scripts/preflight-factory-control-runtime.sh "$PWD"
```

Result: `factory_control_runtime_preflight=ok`

Passed:

```bash
python3 -m py_compile ops/factory_control.py tests/test_factory_runtime_queue_contracts.py
```

Result: success.

Full-suite attempt:

```bash
python3 -m pytest
```

Result: blocked during collection by missing local test dependencies in this lease environment:

- `ModuleNotFoundError: No module named 'pydantic'`
- `ModuleNotFoundError: No module named 'httpx'`

No secrets were printed.

