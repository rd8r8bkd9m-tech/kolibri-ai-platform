# ACTIONS

- Inspected the requested files and the previous direct-server run artifacts under `/var/lib/kolibri-agent/manual-runs/.../out` read-only.
- Added `LeaseHeartbeatError` and a reusable task lease heartbeat monitor to `ops/agent_host.py`.
- Wrapped subprocess, JSON runner, API/local model, and configured image/model paths with heartbeat renewal.
- Classified heartbeat renewal failure as `lease_heartbeat_failed` with structured result artifact.
- Added control-plane `task_status_view()` with `lease_status`, `heartbeat_status`, `heartbeat_age_seconds`, and `seconds_until_lease_expiry`.
- Updated expired lease reaping to renew a task when its `heartbeat_at` is fresh instead of prematurely moving it to retry or dead letter.
- Returned annotated status from task list/detail, lease, heartbeat, complete, annotate, fail, cancel, and agent status paths.
- Added focused fake-runner tests in existing test modules.
- Wrote lease contract and MVP runtime path docs.
