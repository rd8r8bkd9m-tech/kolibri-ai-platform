# P0 Fleet Route Freshness Gate

Task id: `P0_FLEET_ROUTE_FRESHNESS_GATE_2026_07_02`

## State

- Status: implemented and focused regression tests passed.
- Node: `kolibri`
- Runtime: `Linux kolibri 6.8.0-36-generic #36-Ubuntu SMP PREEMPT_DYNAMIC Mon Jun 10 10:49:14 UTC 2024 x86_64`
- Execution location: server/control Agent Host workspace, not a local Mac.

## Change

- `ops/factory_control.py`: `fabric_route()` now classifies heartbeat freshness before route selection.
- Direct `direct_fabric_api` routes require `health=online` and `freshness=fresh`.
- Fallback nodes also require fresh online status, so stale nodes are not promoted as alternates.
- Repair guidance now names fresh heartbeat restoration explicitly.

## Verification

- `hostname && uname -a`
  - Passed; node was `kolibri`.
- `python3 -m pytest tests/test_prompt3_fabric_api_surface.py tests/test_factory_runtime.py -q`
  - Passed: `14 passed in 0.14s`.
- `python3 -m pytest tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py -q`
  - Blocked during collection: `ModuleNotFoundError: No module named 'httpx'`.

## Artifacts

- `docs/agent/runs/2026-07-02-p0-fleet-route-freshness-gate/RESULT.md`
- Regression coverage: `tests/test_prompt3_fabric_api_surface.py::test_fleet_route_blocks_stale_direct_target_and_excludes_stale_fallbacks`

## Blockers

- Adjacent factory-status tests require `httpx`, which is missing from this server Python environment. No dependency install was attempted.

## Next Action

- Install or provide the approved Python dependency environment containing `httpx`, then rerun:
  `python3 -m pytest tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py -q`
