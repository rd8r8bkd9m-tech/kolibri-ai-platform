# Tests

Passed on `primary-candidate` remote server:

```bash
python3 -m py_compile ops/factory_control.py ops/agent_host.py tests/test_factory_capacity_controls.py
git diff --check
python3 -m pytest -q tests/test_factory_capacity_controls.py tests/test_factory_runtime.py tests/test_factory_runtime_queue_contracts.py tests/test_agent_host_runner_contract.py
```

Result: `46 passed in 41.13s`

Broader dependency-free runtime suite:

```bash
python3 -m pytest -q tests/test_factory_capacity_controls.py tests/test_factory_runtime.py tests/test_factory_runtime_queue_contracts.py tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py tests/test_agent_host_permission_contract.py tests/test_agent_host_image_generation.py tests/test_agent_host_telegram_chat.py tests/test_agent_host_direct_mimo.py tests/test_agent_host_runner_contract.py tests/test_factory_control_superfactory.py tests/test_factory_control_runtime_import_path.py tests/test_factory_runtime_contracts.py tests/test_mesh_control_bridge.py tests/test_telegram_gateway.py tests/test_telegram_superfactory_contracts.py tests/test_telegram_superfactory_miniapp.py
```

Result: `126 passed in 44.66s`

Blocked:

```bash
python3 -m pytest -q
```

Blocked reason: `blocked_missing_dependency`; this server environment is missing backend test dependencies `pydantic` and `httpx`.
