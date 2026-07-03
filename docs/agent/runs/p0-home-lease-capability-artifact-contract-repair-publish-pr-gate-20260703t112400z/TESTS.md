# Tests

- `python3 -m py_compile ops/factory_control.py tests/test_factory_runtime.py`
  - Result: passed.
- `python3 -m pytest tests/test_factory_runtime.py -q`
  - Result: passed, `8 passed in 0.05s`.
- `python3 -m pytest tests/test_factory_runtime_contracts.py tests/test_fabric_control.py -q`
  - Result: passed, `9 passed in 0.07s`.
- `python3 -m pytest tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_fabric_control.py -q`
  - Result: passed, `17 passed in 0.10s`.
- `git diff --check`
  - Result: passed.
- `gh --version && gh auth status`
  - Result: blocked because `gh` is not installed in this environment.
