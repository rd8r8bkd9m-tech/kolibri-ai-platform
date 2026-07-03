# Tests

Verification:

- `python -m py_compile ops/agent_host.py tests/test_agent_host_runner_contract.py`
  - Result: failed because `python` is not installed on PATH in this container.
- `python3 -m py_compile ops/agent_host.py tests/test_agent_host_runner_contract.py`
  - Result: passed.
- `python3 -m json.tool docs/agent/dispatcher/envelopes/P0_HOME_AGENT_HOST_NONEMPTY_ARTIFACT_CONTRACT_CANARY_2026_07_03.json >/dev/null`
  - Result: passed.
- `pytest tests/test_agent_host_runner_contract.py tests/test_agent_host_direct_mimo.py tests/test_factory_runtime.py -q`
  - Result: passed, `45 passed in 38.89s`.

No live Agent Host restart or Home deploy was performed.
