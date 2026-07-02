# Result

Status: `blocked_for_p0_exit`

Task id: `P0_30MIN_SECOND_WAVE_PRIMARY_RELEASE_GATE_2026_07_02`

Node: `primary-candidate`

Decision:

- Do not exit P0 from this second 30-minute wave yet.
- Core checked-in runtime contracts passed.
- Live Factory Control primary routes are available.
- Factory Control and Telegram Gateway services are active/running.
- The 30-minute fleet freshness gate failed: `11` fresh nodes and `31` stale
  nodes out of `42` total.

Changed files:

- `docs/agent/runs/2026-07-02-p0-30min-second-wave-primary-release-gate/PLAN.md`
- `docs/agent/runs/2026-07-02-p0-30min-second-wave-primary-release-gate/ACTIONS.md`
- `docs/agent/runs/2026-07-02-p0-30min-second-wave-primary-release-gate/TESTS.md`
- `docs/agent/runs/2026-07-02-p0-30min-second-wave-primary-release-gate/RELEASE_GATE_MATRIX.md`
- `docs/agent/runs/2026-07-02-p0-30min-second-wave-primary-release-gate/RESULT.md`
- `docs/agent/runs/2026-07-02-p0-30min-second-wave-primary-release-gate/NEXT.md`
- `docs/agent/runs/2026-07-02-p0-30min-second-wave-primary-release-gate/REMOTE_RESULT.json`

Verification commands:

- `git diff --check`
- `python3 -m py_compile ops/factory_control.py ops/agent_host.py ops/telegram_gateway.py ops/telegram_superfactory.py backend/factory_status.py backend/main.py`
- `scripts/preflight-factory-control-runtime.sh`
- `python3 -m pytest -q tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_control_runtime_import_path.py tests/test_fabric_control.py tests/test_factory_control_superfactory.py tests/test_agent_host_runner_contract.py tests/test_agent_host_permission_contract.py tests/test_agent_host_direct_mimo.py tests/test_telegram_gateway.py tests/test_telegram_superfactory_contracts.py tests/test_telegram_superfactory_miniapp.py tests/test_mesh_control_bridge.py tests/test_prompt3_fabric_api_surface.py tests/test_agent_host_telegram_chat.py tests/test_agent_host_image_generation.py`
- `node frontend/tests/mobile_layout_guard.mjs`
- `curl` probes for `/health`, `/v1/health`, `/v1/fabric/health`,
  `/v1/fabric/routes`, `/v1/fleet/nodes`, and `/v1/models` on
  `http://10.99.0.10:9101`
- `systemctl show` non-secret status checks for Factory Control and Telegram
  Gateway.

Risks:

- Fleet node cards still overstate availability when judged against the
  30-minute heartbeat requirement.
- Telegram Gateway is active now, but this wave did not prove single-receiver
  ownership because it intentionally avoided Bot API calls and secret-bearing
  logs.
- Broad Python and frontend build signals are still environment-blocked on this
  worktree.

Next exact task:

`P0_FLEET_30MIN_FRESHNESS_REPAIR_AND_THIRD_WAVE_RELEASE_GATE_2026_07_02`
