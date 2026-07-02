# Tests

Command:

```bash
.venv/bin/python -m pytest tests/test_public_api_security.py tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py -q
```

Result:

```text
10 passed in 1.39s
```

Notes:

- System Python was externally managed, so validation used an in-repo `.venv`.
- Dependencies were installed from `backend/requirements.txt` plus `pytest`.
