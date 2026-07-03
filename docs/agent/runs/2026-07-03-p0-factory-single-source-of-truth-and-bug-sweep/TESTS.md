# Tests

## Commands Run

```bash
python3 -m py_compile ops/factory_registry.py ops/factory_control.py ops/agent_host.py ops/kolibri-dispatch
python3 -m pytest -q tests/test_factory_registry.py tests/test_factory_runtime.py tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py tests/test_factory_runtime_queue_contracts.py
```

## Result

- `py_compile`: passed.
- Targeted pytest: `32 passed in 0.14s`.

## Not Run

- Full repository pytest was not run in this sweep.
- Production service restart was not performed.
- GitHub CI was not checked from this branch yet.
- Draft PR CI could not run because branch push is blocked by read-only GitHub SSH credentials on this host.
