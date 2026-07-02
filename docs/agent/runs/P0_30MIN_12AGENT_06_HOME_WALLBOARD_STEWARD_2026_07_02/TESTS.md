# Tests

| Command | Result | Evidence |
| --- | --- | --- |
| `python3 -m pytest -q tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py` | `blocked` | Collection failed with `ModuleNotFoundError: No module named 'httpx'`. This matches the earlier `B3` environment packaging blocker. |
| `python3 -m py_compile backend/factory_status.py backend/main.py ops/factory_control.py ops/mesh_control_bridge.py` | `passed` | Command exited `0`. |
| `python3 -m json.tool docs/agent/dispatcher/envelopes/P0_REPAIR_POST_MERGE_CANARY_RUNTIME_BLOCKERS_2026_07_02.json >/dev/null && python3 -m json.tool docs/agent/dispatcher/envelopes/P0_HOME_FACTORY_TERMINAL_UI_RU_2026_07_01.json >/dev/null` | `passed` | Command exited `0`. |
| `test -f docs/agent/dispatcher/envelopes/P0_30MIN_12AGENT_06_HOME_WALLBOARD_STEWARD_2026_07_02.json && ... || true` | `not_present` | No current task envelope exists in this checkout for this exact task id. |
| `ls docs/agent/runs/2026-07-01-p0-home-factory-terminal-ui-ru 2>/dev/null || true` | `not_present` | No canonical Home terminal wallboard run artifact directory exists in this checkout. |
| `git status --short` | `clean_before_artifacts` | No pre-existing changes were printed before artifact writes. |

Focused contract summary:

- The React wallboard path uses `/api/factory/status`, not `/cluster/status`.
- Backend `build_factory_status` normalizes Control Plane nodes into fresh/degraded/stale counts and does not count stale reported-online nodes as online.
- The checked-in tests cover those contracts, but this runner lacks `httpx`, so they cannot execute here without an approved environment repair.

