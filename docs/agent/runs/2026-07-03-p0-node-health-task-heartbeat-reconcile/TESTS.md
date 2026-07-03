# Tests

Passed:

```text
python3 -m pytest -q tests/test_factory_runtime.py
.........                                                                [100%]
9 passed in 0.09s
```

```text
python3 -m py_compile ops/factory_control.py ops/agent_host.py backend/factory_status.py
```

```text
python3 -m pytest -q tests/test_factory_runtime.py tests/test_prompt3_fabric_api_surface.py tests/test_fabric_control.py
....................                                                     [100%]
20 passed in 0.14s
```

Blocked in this environment:

```text
python3 -m pytest -q tests/test_factory_runtime.py tests/test_factory_status.py
```

Result: collection failed because `httpx` is not installed for `tests/test_factory_status.py`.
