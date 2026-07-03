# Next

- Open or update the PR from `p0/node-health-task-heartbeat-reconcile-2026-07-03` if it is not already under review.
- After merge, deploy Factory Control and confirm NOC `/v1/nodes` no longer marks active workers stale solely because node heartbeat lags task heartbeat.
- Re-run `tests/test_factory_status.py` in an environment with `httpx` installed if backend status normalization coverage is required.

