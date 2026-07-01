# Tests

Server verification:

```bash
git fetch origin pull/96/head:refs/remotes/origin/pr/96
git diff --name-status origin/main...origin/pr/96
python3 -m compileall -q ops/agent_host.py tests/test_agent_host_permission_contract.py
python3 -m pytest -q tests/test_agent_host_permission_contract.py
python3 -m pytest -q tests/test_factory_runtime.py tests/test_agent_host_telegram_chat.py tests/test_agent_host_image_generation.py tests/test_agent_host_permission_contract.py
git diff --check origin/main...HEAD
python3 -m pytest -q tests/test_agent_host_permission_contract.py tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py
```

Server results:

- `tests/test_agent_host_permission_contract.py`: `2 passed`.
- Focused Agent Host/factory runtime suite: `12 passed`.
- Envelope verifier suite: `14 passed in 0.16s`.
- `git diff --check`: clean.

Command-node GitHub evidence after branch update:

- Head: `42625cadb2c0d164e2d82598a8a887d5a9a3d1e1`.
- Changed files: `ops/agent_host.py`, `tests/test_agent_host_permission_contract.py`.
- GitHub check `ci`: completed, success.
- Mergeable: `true`.
- Mergeable state: `clean`.
