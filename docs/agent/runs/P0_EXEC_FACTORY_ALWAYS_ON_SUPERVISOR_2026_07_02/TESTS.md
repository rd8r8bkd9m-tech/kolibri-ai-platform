# Tests

Focused verification:

```bash
python3 -m py_compile ops/factory_control.py
python3 -m pytest tests/test_factory_supervisor_loop.py tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_control_runtime_import_path.py
```

Result:

- `py_compile`: passed
- Pytest: `17 passed`

Covered behavior:

- Supervisor repair dispatch budget is capped at 50%.
- Dead agents are detected from stale heartbeats and receive scoped repair tasks.
- Russian owner summary includes the 50% cap.
- Stuck running tasks are requeued once without duplicate queue entries.
- Existing factory runtime and import path contracts still pass.

Broader suite attempt:

```bash
python3 -m pytest tests
```

Result:

- Blocked during collection by missing local dependency: `ModuleNotFoundError: No module named 'httpx'`.
- `httpx==0.27.0` is declared in `backend/requirements.txt`; the exact repair command is:

```bash
python3 -m pip install -r backend/requirements.txt
```

Additional verification still recommended before live rollout:

```bash
FACTORY_SUPERVISOR_ENABLED=0 python3 ops/factory_control.py --bind 127.0.0.1 --port 9101
curl -s http://127.0.0.1:9101/v1/factory/supervisor
```

Then enable only after confirming live Redis and node registration state:

```bash
FACTORY_SUPERVISOR_ENABLED=1 systemctl restart kolibri-factory-control.service
curl -s http://127.0.0.1:9101/v1/factory/supervisor
```
