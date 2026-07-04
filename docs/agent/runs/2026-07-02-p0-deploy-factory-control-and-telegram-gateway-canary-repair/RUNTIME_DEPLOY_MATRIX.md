# Runtime Deploy Matrix

| ID | Surface | Attempted action | Result | Evidence | Next action |
| --- | --- | --- | --- | --- | --- |
| `fabric-entrypoint` | `/usr/local/bin/kolibri-factory-control` | Install current `ops/factory_control.py` over runtime entrypoint and restart service | `failed_rolled_back` | Service failed with `ModuleNotFoundError: No module named 'telegram_superfactory'`; backup restored | Repair packaging/import path in PR before live deploy |
| `control-plane-health` | `http://10.99.0.10:9101/health` | Verify after rollback | `restored` | HTTP `200` after restoring backup | Keep old entrypoint until packaging fix is merged |
| `fabric-routes` | `/v1/fabric/*`, `/v1/fleet/nodes`, `/v1/models` | Verify after rollback | `still_stale` | HTTP `404` | Deploy only after import-path preflight passes |
| `telegram-runtime` | `kolibri-telegram-gateway.service` | Check service state | `inactive_on_probed_node` | `systemctl is-active` returned `inactive` | Prove canonical receiver before start/restart |
| `agent-host-finalization` | task heartbeat/fail | Observe during Control Plane outage | `fragile` | Agent Host could not post heartbeat/fail: connection refused | Add fallback finalization path or out-of-band result relay |

