# Result

Status: `implemented_not_deployed`

Task id: `P0_PRIMARY_NODE_HEARTBEAT_REPAIR_READONLY_2026_07_02`

Node: `kolibri`

Agent Host lease: `mesh-agent-12:agent-host-mesh-agent-12`

Exact state:

- Remote execution happened on server Agent Host `mesh-agent-12` on host
  `kolibri`, not a local Mac.
- Factory Control live service was active on `10.99.0.10:9101`.
- `primary-candidate` node heartbeat was degraded during the probe:
  `heartbeat_age_seconds=81`, `freshness=degraded`, `reported_health=online`.
- A primary-owned task heartbeat was fresh at the same time:
  `P0_30MIN_12AGENT_05B_RUNNER_CONTRACT_STEWARD_FALLBACK_2026_07_02`
  had heartbeat age 3 seconds and lease owner
  `primary-candidate:agent-host-primary`.
- Live route selection still returned a direct route to `primary-candidate`
  before this patch because `fabric_route()` did not apply heartbeat
  freshness classification.

Implemented fix:

- `ops/factory_control.py`: `fabric_route()` now applies
  `classify_node_freshness()` to registered nodes that include `heartbeat_at`
  before selecting direct or fallback routes.
- `tests/test_fabric_control.py`: added a regression test proving a stale
  `health: online` `primary-candidate` is blocked and a fresh fallback is
  returned.

Verification:

- `pytest -q tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_agent_host_permission_contract.py`
  passed: 13 tests.
- `pytest -q tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_agent_host_permission_contract.py`
  passed: 25 tests.
- Read-only live probes are recorded in `PROBES.md`.

Safety:

- No secrets printed.
- No destructive git commands.
- No force push.
- No push to `main`.
- No service restart.
- No Telegram Bot API mutation.

Required artifacts:

- `PLAN.md`
- `ACTIONS.md`
- `PROBES.md`
- `TESTS.md`
- `NEXT.md`
- `RESULT.md`
- `REMOTE_RESULT.json`

Blockers:

- Live runtime is not updated until an approved deploy canary restarts
  `kolibri-factory-control.service` with a recorded preflight and rollback
  artifact.

Next action:

`P0_DEPLOY_FACTORY_ROUTE_FRESHNESS_GATE_CANARY_2026_07_02`

