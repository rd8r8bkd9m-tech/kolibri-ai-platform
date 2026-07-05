# Release Process

Release evidence for this branch lives in `release/`.

Required files for this pass:

- `release/initial-state.md`
- `release/initial-git-status.txt`
- `release/checklist.md`
- `release/manifest.json`
- `release/final-report.md`

Minimum validation:

```bash
backend/venv/bin/python -m pytest -q tests/test_factory_control_superfactory.py tests/test_telegram_superfactory_miniapp.py tests/test_telegram_superfactory_contracts.py
```

Production deploy and DNS remain approval-gated.
