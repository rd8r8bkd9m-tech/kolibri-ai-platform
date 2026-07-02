# TESTS

Remote agent evidence:

- `pytest -q tests/test_factory_capacity_controls.py` -> `18 passed`
- Adjacent factory suites -> `31 passed`
- `git diff --check` -> clean
- Manual local 1000 empty-poll probe -> `{"200:no_task": 1000}`

Relay verification to run in this clean worktree:

- `python3 -m py_compile ops/factory_control.py tests/test_factory_capacity_controls.py`
- `python3 -m pytest -q tests/test_factory_capacity_controls.py tests/test_factory_runtime.py tests/test_factory_runtime_queue_contracts.py`
- `git diff --check`

Runtime canary was not run in this task by design.
