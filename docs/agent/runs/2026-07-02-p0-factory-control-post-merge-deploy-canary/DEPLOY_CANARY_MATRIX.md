# Deploy Canary Matrix

Status: `passed`

| Surface | Check | Result | Evidence |
| --- | --- | --- | --- |
| Preflight | Ran on target repo path before restart | pass | `factory_control_runtime_preflight=ok` for `/opt/kolibri-ai-platform` |
| Service | `kolibri-factory-control.service` | pass | `active/running`, PID `3588876` |
| Runtime entrypoint | Systemd command | pass | `/usr/bin/python3 /opt/kolibri-ai-platform/ops/factory_control.py` |
| `/health` | HTTP route | pass | HTTP `200` |
| `/v1/health` | HTTP route | pass | HTTP `200` |
| `/v1/fabric/health` | HTTP route | pass | HTTP `200` |
| `/v1/fabric/routes` | HTTP route | pass | HTTP `200` |
| `/v1/fleet/nodes` | HTTP route | pass | HTTP `200` |
| `/v1/models` | HTTP route | pass | HTTP `200` |
| Telegram | No service/API mutation | pass | gateway remained `inactive/dead`; `telegram_touched=false` |
| Rollback | Required or not | not needed | backup exists and route canary passed |

