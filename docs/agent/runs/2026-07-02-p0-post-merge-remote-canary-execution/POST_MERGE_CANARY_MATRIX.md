# Post-Merge Canary Matrix

Current main verified before classification: `c97a0f50e14e3c2c20babfd13fbeb045400f66f2`.

| Surface | Evidence | Classification | Notes |
| --- | --- | --- | --- |
| Agent Host | `kolibri-agent-host.service` active; focused tests included `test_agent_host_runner_contract.py` and `test_agent_host_permission_contract.py`; suite result `89 passed`. | `test_backed_pass_live_service_active` | No write-capable task was submitted during this pass. |
| MIMO | Focused tests included `test_agent_host_direct_mimo.py`; suite result `89 passed`. | `test_backed_pass` | Live MIMO provider/auth execution was not invoked; no secrets were requested or printed. |
| Control Plane freshness | `kolibri-factory-control.service` active; `/health` returned `status=ok`, `redis=PONG`, `spool_count=0`, `spool_replayed=0`, timestamp `2026-07-01T21:07:56.908979+00:00`. | `health_pass_api_surface_blocked` | Fast-health tests blocked on missing `httpx`; `/v1/...` routes returned 404 on the probed listener. |
| Fabric API | Contract tests `test_fabric_control.py` and `test_prompt3_fabric_api_surface.py` passed inside the focused suite. | `contract_pass_live_route_blocked` | Live `/v1/fabric/health`, `/v1/fleet`, and `/v1/status` returned 404 at `10.99.0.10:9101`. |
| Telegram runtime | `test_telegram_gateway.py` passed in the focused suite; `kolibri-telegram-gateway.service` is inactive/dead. | `contract_pass_live_runtime_blocked` | No Telegram API mutation, webhook change, token read, or message consumption was performed. |
| GitHub PR queue | `git ls-remote` showed `main` at `c97a0f50...`, 68 pull refs, and refs for #83/#85/#89/#91/#92/#96/#97/#98. | `ref_visibility_pass_live_metadata_blocked` | `gh` is unavailable, so live draft/mergeability/check status was not classified. |

Overall result: `runtime_blocked_after_test_canary`.

This pass proves the checked-in post-merge contracts on the server node, but live canary completion is blocked by the inactive Telegram gateway, missing live Fabric `/v1` routes on the probed control listener, missing `httpx` in the node Python environment for factory-status tests, and lack of `gh` for PR queue metadata.

