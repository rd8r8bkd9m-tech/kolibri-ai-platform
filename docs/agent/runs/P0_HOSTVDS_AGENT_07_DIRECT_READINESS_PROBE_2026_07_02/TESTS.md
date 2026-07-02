# Verification

Verification commands and results:

| Check | Result |
| --- | --- |
| `git status --short` before docs | clean |
| `df -h /` | `/dev/vda1` total `99G`, used `45G`, available `49G`, use `48%` |
| `command -v gh` | `gh_missing` |
| `command -v codex` | `codex_present` |
| `command -v python3` | `python3_present` |
| `command -v curl` | `curl_present` |
| `systemctl is-active kolibri-factory-control.service` | `active` |
| `systemctl is-enabled kolibri-factory-control.service` | `enabled` |
| `systemctl is-active kolibri-agent-host.service` | `active` |
| `systemctl is-enabled kolibri-agent-host.service` | `enabled` |
| `curl http://10.99.0.10:9101/health` | HTTP `200` |
| `curl http://10.99.0.10:9101/v1/health` | HTTP `200` |
| `curl http://10.99.0.10:9101/v1/fabric/health` | HTTP `200` |
| `curl http://10.99.0.10:9101/v1/fabric/routes` | HTTP `200` |
| `curl http://10.99.0.10:9101/v1/fleet/nodes` | HTTP `200` |
| `curl http://10.99.0.10:9101/v1/models` | HTTP `200` |
| `bash scripts/preflight-factory-control-runtime.sh "$PWD"` | `factory_control_runtime_preflight=ok` |

Local route notes:
- `127.0.0.1:9101` did not answer; the service is bound to `10.99.0.10:9101`.
- `127.0.0.1:8000` listened but returned HTTP `404` for sampled Control Plane health routes.

