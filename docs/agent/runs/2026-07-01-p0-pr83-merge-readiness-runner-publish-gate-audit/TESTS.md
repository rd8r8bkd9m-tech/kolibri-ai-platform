# Tests

Verification used Python 3.12.3 through `python3` and `.venv/bin/python`.
No `python` command was used.

Commands:

```bash
python3 -m py_compile ops/agent_host.py
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip pytest -r backend/requirements.txt
.venv/bin/python -m py_compile ops/agent_host.py
.venv/bin/python -m pytest tests/test_agent_host_runner_contract.py -q
.venv/bin/python -m pytest tests/test_agent_host* -q
.venv/bin/python -m pytest -q
```

Results:

- `python3 -m py_compile ops/agent_host.py`: passed.
- First `python3 -m pytest tests/test_agent_host_runner_contract.py -q` attempt:
  blocked because system Python had no `pytest` module.
- `.venv/bin/python -m py_compile ops/agent_host.py`: passed.
- `.venv/bin/python -m pytest tests/test_agent_host_runner_contract.py -q`:
  15 passed.
- `.venv/bin/python -m pytest tests/test_agent_host* -q`: 21 passed.
- `.venv/bin/python -m pytest -q`: 75 passed, 1 external `reportlab`
  deprecation warning.

Regression coverage added:

- Missing required artifact blocks publish with `push_attempted: false`.
- Passing preflight allows `git push` and preserves completed status.
