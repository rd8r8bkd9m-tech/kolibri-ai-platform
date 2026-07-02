# Tests

Verification run on `mesh-agent-04`:

```text
python3 -m py_compile ops/agent_host.py ops/factory_control.py
```

```text
python3 -m pytest -q tests/test_agent_host_runner_contract.py tests/test_agent_host_direct_mimo.py
36 passed
```

```text
python3 -m pytest -q tests/test_fabric_control.py tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py
20 passed
```

```text
python3 -m pytest -q tests/test_agent_host_telegram_chat.py tests/test_agent_host_image_generation.py tests/test_agent_host_permission_contract.py
10 passed
```

Diff checks:

```text
git diff --check -- ops/agent_host.py ops/factory_control.py tests/test_agent_host_runner_contract.py
```

The repair branch was prepared from `origin/main` and contains only the allowed
scope plus this required artifact directory.
