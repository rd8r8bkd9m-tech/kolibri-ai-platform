# Tests

Verification commands:

```bash
python3 -m pytest tests/test_agent_host_runner_contract.py -q
python3 -m pytest tests/test_agent_host_runner_contract.py tests/test_factory_runtime.py -q
git diff --check
```

Observed results:

- `python3 -m pytest tests/test_agent_host_runner_contract.py -q`: 32 passed in 34.78s.
- `python3 -m pytest tests/test_agent_host_runner_contract.py tests/test_factory_runtime.py -q`: 39 passed in 34.79s.
- `git diff --check`: passed.

Expected coverage:

- Required artifacts block completion when missing.
- Canonical run artifacts require exact `PLAN.md`, `ACTIONS.md`, `TESTS.md`, `RESULT.md`, and `NEXT.md`.
- Unsupported task kind posts `/fail` with `error_type: runner_contract_blocked`.
- Unsupported required capability posts `/fail` with `error_type: runner_contract_blocked`.
- Read-only, no-push, write-scope, product-code, backend verifier environment, and runner auth redaction regressions remain covered.
