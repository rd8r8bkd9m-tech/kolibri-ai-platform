# Tests

Passed:
- `python3 -m pytest -q tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py`
  - Result: `29 passed in 0.26s`
- `python3 -m py_compile ops/factory_control.py ops/kolibri-dispatch`
  - Result: passed

Probe:
- `hostname`
  - Result: `kolibri`
- `./ops/kolibri-dispatch backlog-audit`
  - Result: blocked by live deployed control plane HTTP 404 for `/v1/tasks/backlog/audit`.

Not run:
- Full repository test suite, because the focused contract surface covers this change and prior run artifacts show environment-sensitive backend dependencies can block unrelated tests.
