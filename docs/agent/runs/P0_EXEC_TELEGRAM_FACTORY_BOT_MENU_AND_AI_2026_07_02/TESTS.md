# Tests

Focused suite:

```bash
python3 -m pytest tests/test_telegram_gateway.py tests/test_telegram_superfactory_contracts.py tests/test_telegram_superfactory_miniapp.py tests/test_factory_control_superfactory.py tests/test_prompt3_fabric_api_surface.py
```

Result:

```text
54 passed in 1.36s
```

Syntax check:

```bash
python3 -m py_compile ops/telegram_gateway.py ops/telegram_superfactory.py ops/factory_control.py
```

Result: passed.

Full suite:

```bash
python3 -m pytest
```

Result: blocked during collection by missing local Python dependencies:

```text
ModuleNotFoundError: No module named 'pydantic'
ModuleNotFoundError: No module named 'httpx'
```

Exact repair command for this environment:

```bash
python3 -m pip install -r backend/requirements.txt httpx pytest
```

Notes:

- `python -m pytest ...` was not available because `python` is not on PATH in this environment.
- No live Telegram API calls were made.
- No Telegram token value was printed.
