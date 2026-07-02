# TESTS

Passed on `primary-candidate`:

- `python3 -m py_compile ops/factory_control.py`
- `python3 -m pytest tests/test_factory_capacity_controls.py -q` -> `19 passed`
- `python3 -m pytest tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py -q` -> `15 passed`
- Local subprocess stage probe with `FACTORY_HTTP_MAX_WORKERS=256`:
  - stages `20/50/100/250/500/1000`
  - all empty polls returned `200/no_task`
  - server threads plateaued at `65`
  - fd count stayed `4`
- `git diff --check` -> clean

Blocked/non-gating:

- `tests/test_factory_status.py` collection failed because this node lacks optional dependency `httpx`. This is unrelated to the Control Plane lease path and was not used as a release pass.

Runtime canary was not run by the remote implementation task.
