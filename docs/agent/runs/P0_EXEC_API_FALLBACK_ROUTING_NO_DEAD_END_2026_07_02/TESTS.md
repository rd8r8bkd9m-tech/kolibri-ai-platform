# Tests

Failed environment probe:

```text
python -m pytest tests/test_prompt3_fabric_api_surface.py tests/test_fabric_control.py -q
```

Result: failed because `python` is not installed in this runtime.

Successful verification:

```text
python3 -m pytest tests/test_prompt3_fabric_api_surface.py tests/test_fabric_control.py -q
```

Result: `13 passed in 0.19s`

```text
python3 -m pytest tests/test_factory_control_superfactory.py tests/test_factory_control_runtime_import_path.py tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py -q
```

Result: `16 passed in 0.78s`

