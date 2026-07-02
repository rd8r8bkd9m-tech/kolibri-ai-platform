# Tests

Passed:

```bash
python3 -m py_compile ops/mimo_pool_policy.py ops/agent_host.py ops/factory_control.py backend/factory_status.py
```

```bash
python3 -m pytest -q tests/test_mimo_pool_policy.py tests/test_factory_status.py tests/test_agent_host_runner_contract.py
```

Result: `37 passed in 34.73s`

```bash
./scripts/preflight-factory-control-runtime.sh .
```

Result: `factory_control_runtime_preflight=ok`

Dependency note: the local environment did not have `httpx` installed initially. `backend/factory_status.py` now only requires `httpx` when live status fetching is called, so normalization tests run in the minimal backend test environment.
