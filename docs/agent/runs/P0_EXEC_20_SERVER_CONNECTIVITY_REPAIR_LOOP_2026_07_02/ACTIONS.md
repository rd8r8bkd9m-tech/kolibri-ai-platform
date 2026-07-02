# Actions

## Implemented

- Added `OWNER_SERVER_CATALOG` for the canonical 20 owner servers.
- Added owner-server alias handling for mesh/card identities such as
  `mesh-agent-01` and `mesh-9fts`.
- Added `owner_server_repair_plan()` and safe per-node repair envelope
  generation in `ops/factory_control.py`.
- Added `GET /v1/fleet/repair-plan` to the Control Plane handler.
- Added `./ops/kolibri-dispatch repair-plan` with:
  - `--local` fallback planner mode.
  - `--write-dir` per-node envelope output.
  - `--submit` live `/v1/tasks` dispatch.
- Added tests covering canonical 20 coverage, blocked repair envelopes, alias
  identity repair, and dispatcher command exposure.

## Executed

- Tried live `GET /v1/fleet/repair-plan`; current deployed Control Plane
  returned HTTP 404, so this route is not deployed yet.
- Generated 20 per-node repair envelopes under:
  `docs/agent/runs/P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02/repair-envelopes/`
- Submitted the 20 repair envelopes through the existing live `/v1/tasks`
  endpoint.
- Verified all 20 submitted task IDs exist and are in `queued` state.

## Dispatched Task IDs

- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-HOME`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-MAIN`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-UIAP`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-QJNS`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-9FTS`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-NEW`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-PRIMARY_CANDIDATE`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-AGENT_01`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-AGENT_02`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-AGENT_03`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-AGENT_04`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-AGENT_05`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-AGENT_06`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-AGENT_07`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-AGENT_08`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-AGENT_09`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-HIGHLOAD`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-PARIS`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-RESERVE242`
- `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-SERVER_KFRM`

