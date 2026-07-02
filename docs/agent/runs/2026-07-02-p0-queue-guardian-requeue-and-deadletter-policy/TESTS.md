# Tests

Task id: `P0_QUEUE_GUARDIAN_REQUEUE_AND_DEADLETTER_POLICY_2026_07_02`

Status: `passed`

Lease owner: `mesh-agent-04:autonomous_engineer`

Verification commands:

```bash
python3 -m pytest tests/test_factory_runtime_queue_contracts.py tests/test_factory_runtime.py
python3 -m py_compile ops/factory_control.py
python3 -m json.tool docs/agent/runs/2026-07-02-p0-queue-guardian-requeue-and-deadletter-policy/REMOTE_RESULT.json >/dev/null
test -f docs/agent/runs/2026-07-02-p0-queue-guardian-requeue-and-deadletter-policy/PLAN.md
python3 -m pytest tests
```

Results:

- `13 passed in 0.10s`
- `ops/factory_control.py` compiled successfully.
- `REMOTE_RESULT.json` is valid JSON.
- Required run artifacts exist.
- Broad `python3 -m pytest tests` was attempted and blocked during collection by missing environment dependency `httpx` from `tests/test_factory_status.py`.

Blockers:

- Full test suite requires `httpx` in the local Python environment.
