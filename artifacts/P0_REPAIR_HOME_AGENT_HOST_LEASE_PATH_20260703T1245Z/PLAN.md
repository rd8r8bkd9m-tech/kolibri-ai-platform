# PLAN.md — Repair Home Agent Host Lease Path

## Problem
Home kiosk deploy tasks are leaseable after Control Plane P0 SOT deploy but remain queued. The Home node's FABRIC_NODE_CATALOG entry lacked `agent_host_api` in its `api_paths`, preventing fleet routing from designating Home as an agent host. Without this, tasks routed through the Fabric API would never reach the Home agent host for lease.

## Root Cause
1. **Missing `agent_host_api` path**: `FABRIC_NODE_CATALOG["home"].api_paths` was `["fabric_api", "fallback_relay"]` — missing `agent_host_api`. Fleet topology and route checks use this to determine which nodes can handle agent tasks.
2. **Node role mismatch**: Home was cataloged as `command_node_gateway` only, not as a node that can execute agent-hosted tasks.

## Changes
- `ops/factory_control.py:92-99` — Update `FABRIC_NODE_CATALOG["home"]`:
  - Add `"agent_host_api"` to `api_paths`
  - Update `role` to `"command_node_gateway_agent_host"`
- `scripts/deploy.sh:42-46` — Update `deploy_home()` to also deploy `agent_host.py` and `factory_control.py` to Home, and start the agent host with `node_id=home` and `runner:mimo,generic_implementation` capabilities.
- `scripts/verify-home-agent-host-lease.sh` — New verification script that:
  1. Checks factory control health
  2. Registers Home node with correct identity
  3. Sends heartbeat
  4. Verifies node registration
  5. Verifies fleet routing
  6. Tests lease request with `node_id=home` and `runner:mimo` capability
  7. Produces artifact JSON report
