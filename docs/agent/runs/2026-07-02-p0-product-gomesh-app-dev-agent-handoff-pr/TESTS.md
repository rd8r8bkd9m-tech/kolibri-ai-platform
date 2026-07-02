# Tests

Verification run:

```bash
git diff --check
python3 -m py_compile ops/factory_control.py
python3 -m pytest tests/test_factory_control_gomesh_handoff.py tests/test_prompt3_fabric_api_surface.py -q
python3 -m pytest tests/test_factory_runtime_queue_contracts.py tests/test_factory_runtime_contracts.py tests/test_factory_control_superfactory.py -q
rg --no-ignore -n '[0-9]{6,}:[A-Za-z0-9_-]{20,}|[A-Za-z0-9_]*(TOKEN|SECRET|PASSWORD|COOKIE|API_KEY|CHAT_ID)=[^ ]+' ops/factory_control.py tests/test_factory_control_gomesh_handoff.py tests/test_prompt3_fabric_api_surface.py docs/agent/runs/2026-07-02-p0-product-gomesh-app-dev-agent-handoff-pr && exit 1 || true
```

Results:
- `git diff --check`: passed.
- `python3 -m py_compile ops/factory_control.py`: passed.
- Focused pytest: `9 passed in 0.18s`.
- Adjacent factory pytest: `10 passed in 0.07s`.
- Secret-pattern scan: passed with no matches.

Broader attempted smoke:

```bash
python3 -m pytest tests/test_factory_runtime_queue_contracts.py tests/test_factory_runtime_contracts.py tests/test_factory_control_superfactory.py tests/test_factory_status.py -q
```

Result: blocked during collection because this runtime does not have `httpx`,
which is imported by `backend/factory_status.py` through
`tests/test_factory_status.py`.
