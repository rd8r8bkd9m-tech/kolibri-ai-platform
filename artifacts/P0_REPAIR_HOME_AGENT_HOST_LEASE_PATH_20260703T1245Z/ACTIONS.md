# ACTIONS.md — Repair Home Agent Host Lease Path

## Completed Actions
1. Updated `FABRIC_NODE_CATALOG["home"]` in `ops/factory_control.py` to add `agent_host_api` path and update role.
2. Updated `deploy_home()` in `scripts/deploy.sh` to deploy agent host and factory control to Home with correct identity.
3. Created `scripts/verify-home-agent-host-lease.sh` diagnostic script.
4. Created artifact directory and verification report.
5. Ran full test suite — 164 tests pass (pre-existing `reportlab` import error excluded).
6. Ran unit tests confirming:
   - Home node has `agent_host_api` in fabric catalog
   - `compatible()` accepts `owner_remote_task` with `runner:mimo` for Home
   - `compatible()` rejects tasks targeted to wrong node or missing capability
   - `runner_capability_names("mimo")` returns correct set
