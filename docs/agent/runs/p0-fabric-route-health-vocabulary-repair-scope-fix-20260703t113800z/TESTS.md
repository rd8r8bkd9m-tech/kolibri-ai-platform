# Tests

- Passed: `pytest tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py tests/test_factory_runtime.py` (`21 passed`)
- Passed: `python3 -m py_compile ops/factory_control.py`
- Environment note: `python -m py_compile ops/factory_control.py` could not run because `python` is not installed in this runner; `python3` is the available interpreter.
