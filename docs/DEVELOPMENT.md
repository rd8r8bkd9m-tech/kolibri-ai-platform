# Development

Use the branch-local Python environment for tests:

```bash
backend/venv/bin/python -m compileall -q backend ops scripts
backend/venv/bin/python -m pytest -q tests/test_factory_control_superfactory.py tests/test_telegram_superfactory_miniapp.py tests/test_telegram_superfactory_contracts.py
```

Frontend checks should use the package manager already present in `frontend/`.

Do not run live deploy/bootstrap/DNS actions without approval.
