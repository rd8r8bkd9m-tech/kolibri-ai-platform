# Tests

Environment:

- Python: `/Users/kolibri/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`
- Version: Python 3.12.13
- Temporary venv: `/tmp/kolibri-p0-runner-contract-py312-venv`

Commands run:

```bash
/Users/kolibri/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m venv /tmp/kolibri-p0-runner-contract-py312-venv
/tmp/kolibri-p0-runner-contract-py312-venv/bin/python -m pip install pytest -r backend/requirements.txt
/tmp/kolibri-p0-runner-contract-py312-venv/bin/python -m py_compile ops/agent_host.py
/tmp/kolibri-p0-runner-contract-py312-venv/bin/python -m pytest tests/test_agent_host_runner_contract.py -q
/tmp/kolibri-p0-runner-contract-py312-venv/bin/python -m pytest tests/test_agent_host* -q
/tmp/kolibri-p0-runner-contract-py312-venv/bin/python -m pytest tests/test_factory_runtime.py -q
/tmp/kolibri-p0-runner-contract-py312-venv/bin/python -m pytest -q
```

Results:

- `tests/test_agent_host_runner_contract.py`: 13 passed.
- `tests/test_agent_host*`: 19 passed.
- `tests/test_factory_runtime.py`: 4 passed.
- Full suite: 73 passed, 1 warning.

Notes:

- A first full-suite attempt on the Homebrew default Python 3.14 failed during
  dependency installation because pinned `pydantic-core==2.23.2` depends on a
  PyO3 version that supports up to Python 3.13. The successful full run used
  Python 3.12.13, matching the CI workflow family.
- The one full-suite warning is from `reportlab` using deprecated
  `ast.NameConstant`; it is external to this change.
