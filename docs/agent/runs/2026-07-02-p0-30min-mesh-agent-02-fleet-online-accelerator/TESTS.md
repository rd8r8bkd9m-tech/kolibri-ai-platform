# Tests

Commands run:

```bash
python3 -m pytest -q tests/test_factory_runtime.py tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py
python3 -m compileall -q ops backend scripts
```

Result:

- `19 passed in 0.15s`
- Compileall completed with no output and exit code `0`.

