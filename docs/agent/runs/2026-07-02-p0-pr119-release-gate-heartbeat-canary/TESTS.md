# TESTS

Commands run from clean worktree:

- `python3 -m py_compile ops/agent_host.py ops/factory_control.py ops/kolibri-dispatch`: passed.
- `python3 -m pytest -q tests/test_agent_host_runner_contract.py`: passed, 34 passed.
- `python3 -m pytest -q tests/test_agent_host_direct_mimo.py`: passed, 3 passed.
- `python3 -m pytest -q tests/test_factory_runtime.py`: passed, 9 passed.
- `python3 -m pytest -q`: blocked during collection by missing local dependencies:
  - `ModuleNotFoundError: No module named 'pydantic'` from `backend/document_engine.py`.
  - `ModuleNotFoundError: No module named 'httpx'` from `backend/factory_status.py`.

GitHub checks:

- PR #119 metadata fetched through GitHub connector.
- PR state: open draft, mergeable, not merged.
- Reviews: none.
- Commit status contexts for `1aab1a2833965a5e9c70dbe685c9d3e85849f070`: none reported.

Runtime probes:

- `curl --max-time 5 http://10.99.0.10:9101/health`: timed out.
- `curl --max-time 5 http://10.99.0.10:9101/v1/nodes`: timed out.
- `journalctl -u kolibri-factory-control.service` showed recent `POST /v1/tasks/lease` 500 responses and BrokenPipe traces.
