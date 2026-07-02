# Actions

Implemented:

- Added supervisor configuration to `ops/factory_control.py`:
  - `FACTORY_SUPERVISOR_ENABLED`
  - `FACTORY_SUPERVISOR_INTERVAL`
  - `FACTORY_SUPERVISOR_AGENT_DEAD_AFTER`
  - `FACTORY_SUPERVISOR_TASK_STUCK_AFTER`
  - `FACTORY_SUPERVISOR_REPAIR_CAP_RATIO`, clamped to `0.5`
  - `FACTORY_SUPERVISOR_REPAIR_HORIZON_SECONDS`
- Made queue enqueue idempotent to avoid duplicate task IDs during automatic requeue paths.
- Added supervisor functions:
  - health check through Redis `PING`
  - dead agent classification from node heartbeat freshness
  - dead node marking
  - repair task dispatch with `kind=repair_dead_agent`
  - stuck running/leased/review task requeue or dead-lettering
  - Russian owner summary field `owner_summary_ru`
- Added endpoints:
  - `GET /v1/factory/supervisor` for read-only status
  - `POST /v1/factory/supervisor/run` for a scoped manual cycle
- Started a daemon supervisor thread from `main()` only when `FACTORY_SUPERVISOR_ENABLED` is enabled.
- Added focused tests in `tests/test_factory_supervisor_loop.py`.

Safety notes:

- No secrets were printed.
- No destructive git command was used.
- No push to `main` or force push was attempted.
- The implementation is reversible by disabling `FACTORY_SUPERVISOR_ENABLED` and restarting the service.
