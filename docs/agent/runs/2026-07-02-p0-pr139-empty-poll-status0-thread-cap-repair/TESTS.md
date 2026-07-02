# TESTS

Remote server test evidence:

- `python3 -m py_compile ops/factory_control.py tests/test_factory_capacity_controls.py`
  - passed
- `python3 -m pytest tests/test_factory_capacity_controls.py -q`
  - `20 passed`
- `python3 -m pytest tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_control_runtime_import_path.py -q`
  - `14 passed`
- `git diff --check`
  - passed

Runtime canary evidence:

- Not run in this commit.
- Required next gate: deploy only `ops/factory_control.py` to `primary-candidate`, restart `kolibri-factory-control.service`, and run the strict stages `20/50/100/250/500/1000` lease-storm canary.
