# Tests

Commands run:

```bash
python3 -m compileall -q ops/agent_host.py ops/factory_control.py
python3 -m pytest -q tests/test_agent_host_runner_contract.py tests/test_factory_runtime.py
KOLIBRI_QJNS_UIAP_WORKER_POOL=1 KOLIBRI_NODE_ID=qjns KOLIBRI_AGENT_MIN_DISK_FREE_GB=1 scripts/preflight-agent-worker-pool.sh .
```

Results:

- `compileall`: passed.
- `pytest`: `42 passed in 36.91s`.
- preflight: passed locally with worker pool ready, MIMO available, max inflight `1`, and no readiness blockers.
