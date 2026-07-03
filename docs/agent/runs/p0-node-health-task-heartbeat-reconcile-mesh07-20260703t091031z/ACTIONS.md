# Actions

- Added active task heartbeat helpers in `ops/factory_control.py`.
- Wired `/v1/nodes` to load task records once per request and reconcile each node card with the freshest valid active task for that node.
- Preserved original node heartbeat fields as `node_freshness`, `node_health`, and `node_heartbeat_age_seconds`.
- Added runtime tests in `tests/test_factory_runtime.py`.
- Salvaged this artifact directory after the original mesh07 attempt failed with `required_artifacts_missing`.

