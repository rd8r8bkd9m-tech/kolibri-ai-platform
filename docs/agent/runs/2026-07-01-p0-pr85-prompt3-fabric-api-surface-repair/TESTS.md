# Tests

Commands run:

```text
python3 -m pytest tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py -q
```

Result:

```text
11 passed in 0.23s
```

Command run:

```text
/tmp/kolibri-p0-pr85-prompt3-venv/bin/python -m pytest -q
```

Result:

```text
71 passed, 1 warning in 4.40s
```

Note: system `python` was unavailable and system `python3 -m pytest -q` lacked project dependencies (`pydantic`, `httpx`), so full verification used a temporary venv at `/tmp/kolibri-p0-pr85-prompt3-venv`.
