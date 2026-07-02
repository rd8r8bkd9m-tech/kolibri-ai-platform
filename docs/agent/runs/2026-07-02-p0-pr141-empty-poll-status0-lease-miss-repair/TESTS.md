# TESTS

Passed:

- `python3 -m pytest tests/test_factory_capacity_controls.py -q`
  - `27 passed in 7.09s`
- `python3 -m pytest tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py -q`
  - `15 passed in 0.11s`

Coverage added:

- 1000 concurrent logical leases must lease all 1000 created tasks.
- 1000 warmed empty HTTP lease polls must all return `200/no_task`.
- Warmed empty lease polls can be answered before entering the worker executor.
- Persisted queued-task recovery sweeps the queued index when the bounded random sample misses a compatible task.

Additional verification after exact artifact relay:

- python3 -m py_compile ops/factory_control.py tests/test_factory_capacity_controls.py -> passed
- python3 -m pytest tests/test_factory_capacity_controls.py tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_control_runtime_import_path.py tests/test_factory_control_superfactory.py -q -> 47 passed in 7.30s
- bash scripts/preflight-factory-control-runtime.sh -> factory_control_runtime_preflight=ok
- git diff --check -> passed
