# Tests

Executed focused verification:

- `python3 -m py_compile ops/agent_host.py`
- `python3 -m pytest -q tests/test_agent_host_runner_contract.py` (`38 passed in 45.15s`)
- `git diff --check -- ops/agent_host.py tests/test_agent_host_runner_contract.py docs/agent/runs/p0-agent-host-artifact-path-relay-mesh13-20260703t092245z`
- `test -s` for all five required run artifacts in `docs/agent/runs/p0-agent-host-artifact-path-relay-mesh13-20260703t092245z/`
