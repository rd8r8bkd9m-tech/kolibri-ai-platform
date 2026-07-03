# Tests

Executed checks:

- `python3 -m pytest -q tests/test_agent_host_runner_contract.py tests/test_agent_host_permission_contract.py`
  - result: `39 passed in 38.74s`
- `python3 -m compileall ops tests`
  - result: passed
- `git diff --check`
  - result: passed

No package manager commands were run outside existing test-local verification
paths for this task.
