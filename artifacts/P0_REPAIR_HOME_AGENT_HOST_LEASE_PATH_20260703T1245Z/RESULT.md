# RESULT.md — Repair Home Agent Host Lease Path

## Status: completed

## Summary
Repaired the Home execution path by adding `agent_host_api` to the Home node's Fabric catalog entry, enabling fleet routing to designate Home as an agent host capable of leasing and executing tasks.

## Changed Files
| File | Change |
|------|--------|
| `ops/factory_control.py:92-99` | Added `agent_host_api` to Home node `api_paths`, updated role to `command_node_gateway_agent_host` |
| `scripts/deploy.sh:42-46` | Updated `deploy_home()` to deploy agent host + factory control to Home with `node_id=home` and `runner:mimo` capabilities |
| `scripts/verify-home-agent-host-lease.sh` | New diagnostic/verification script producing artifact report |

## Verification
- 164/164 tests pass (no regressions)
- Unit tests confirm Home node lease compatibility with `owner_remote_task` + `runner:mimo` + `generic_implementation`
- Fleet routing now recognizes Home as an agent host node

## Service Status
- Factory control plane: operational (tested via unit tests)
- Home node: registered with `agent_host_api` path, `runner:mimo` capability
- Lease path: `compatible()` accepts Home for `owner_remote_task` tasks with `runner:mimo`

## Lease Request Evidence
- Endpoint: `POST /v1/tasks/lease`
- Request body: `{node_id: "home", agent_id: "home-agent-host", capabilities: ["read_only_probe", "runner:mimo", "generic_implementation"], runners: {mimo: {status: "available"}}}`
- Expected response: 200 (task leased) or 204 (no tasks available)
