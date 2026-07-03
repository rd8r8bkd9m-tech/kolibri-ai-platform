# Actions

- Cloned `origin/main` into the assigned empty worktree.
- Added active task heartbeat reconciliation helpers in `ops/factory_control.py`.
- Wired `/v1/nodes` to load active tasks once per request and reconcile each classified node card against the freshest active task for that node.
- Preserved original node heartbeat evidence as `node_freshness`, `node_health`, and `node_heartbeat_age_seconds`.
- Added explicit task evidence fields: `active_task`, `active_task_state`, `active_task_heartbeat_at`, `active_task_heartbeat_age_seconds`, and `active_task_lease_until`.
- Added tests in `tests/test_factory_runtime.py` for:
  - stale node heartbeat plus fresh running task heartbeat becomes an effective fresh/online node card with `status=running_with_stale_node_heartbeat`;
  - expired task lease does not mask a truly stale/dead node.
