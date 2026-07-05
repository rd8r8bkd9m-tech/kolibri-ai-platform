# Agent Onboarding

1. Read `.kolibri/AGENT_START_HERE.md`.
2. Read `AGENTS.md`.
3. Read `docs/SOURCE_OF_TRUTH.md`.
4. Run `git status --short`.
5. Use `backend/venv/bin/python` for pytest in this branch.

Minimum safe validation:

```bash
backend/venv/bin/python -m compileall -q backend ops scripts
backend/venv/bin/python -m pytest -q tests/test_factory_control_superfactory.py tests/test_telegram_superfactory_miniapp.py tests/test_telegram_superfactory_contracts.py
```

Do not read or print `ops/telegram.env`.
