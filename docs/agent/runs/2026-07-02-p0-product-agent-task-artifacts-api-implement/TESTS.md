# Tests

Passed:

```text
python3 -m pytest -q tests/test_prompt3_fabric_api_surface.py tests/test_fabric_control.py tests/test_factory_runtime_contracts.py
18 passed in 0.24s
```

```text
python3 -m py_compile ops/factory_control.py tests/test_prompt3_fabric_api_surface.py
passed
```

```text
python3 -m pytest -q tests/test_prompt3_fabric_api_surface.py tests/test_fabric_control.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py tests/test_telegram_superfactory_contracts.py tests/test_telegram_gateway.py tests/test_agent_host_runner_contract.py
95 passed in 40.16s
```

Blocked by missing local dependencies:

```text
python3 -m pytest -q tests backend/tests
ModuleNotFoundError: No module named 'httpx'
ModuleNotFoundError: No module named 'pydantic'
```
