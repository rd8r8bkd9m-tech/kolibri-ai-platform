# Tests

Passed:

```bash
python3 -m py_compile ops/agent_host.py ops/factory_control.py ops/telegram_gateway.py
python3 -m pytest tests/test_agent_host_runner_contract.py -q
python3 -m pytest tests/test_factory_runtime.py tests/test_telegram_gateway.py -q
python3 -m pytest tests/test_agent_host_runner_contract.py tests/test_agent_host_telegram_chat.py tests/test_agent_host_image_generation.py -q
git diff --name-only origin/main...HEAD | rg '^docs/superfactory' || true
```

Results:

- `tests/test_agent_host_runner_contract.py`: `31 passed in 36.57s`.
- `tests/test_factory_runtime.py tests/test_telegram_gateway.py`: `38 passed in 1.17s`.
- Agent Host chat/runner suite: `37 passed in 40.73s`.
- `docs/superfactory` overlap check produced no paths.
