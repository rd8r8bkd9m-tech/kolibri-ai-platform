# TESTS

Planned commands:

- `python3 -m pytest -q tests/test_agent_host_runner_contract.py`
- `python3 -m pytest -q tests/test_agent_host_direct_mimo.py`
- `python3 -m pytest -q tests/test_factory_runtime.py`
- `python3 -m pytest -q`

Initial environment note:

- `python` is not installed in this shell; tests are run with `python3`.

Results:

- `python3 -m py_compile ops/agent_host.py ops/factory_control.py ops/kolibri-dispatch`: passed_local.
- `python3 -m pytest -q tests/test_agent_host_runner_contract.py`: passed_local, 34 passed.
- `python3 -m pytest -q tests/test_agent_host_direct_mimo.py`: passed_local, 3 passed.
- `python3 -m pytest -q tests/test_factory_runtime.py`: passed_local, 9 passed.
- `python3 -m pytest -q`: blocked_missing_dependency. Collection failed because local Python is missing `pydantic` and `httpx`.

Required behavior checks:

- Fake long-running task longer than `FACTORY_LEASE_DURATION`: passed_local via fake expired lease with fresh heartbeat renewal.
- Heartbeat refresh extends `lease_until`: passed_local.
- Task completes after multiple lease refresh cycles: passed_local.
- Task does not dead-letter while heartbeat succeeds: passed_local.
- Task fails clearly when heartbeat fails: passed_local.
- Direct MIMO long-running path uses heartbeat mechanism: passed_local.
- Codex-like long runner uses heartbeat mechanism: passed_local.
- FormulaLM/crawler-like long runner uses heartbeat mechanism: passed_local through API long-runner path.
- Dispatch/status exposes final state clearly: passed_local through annotated control-plane task status fields.
