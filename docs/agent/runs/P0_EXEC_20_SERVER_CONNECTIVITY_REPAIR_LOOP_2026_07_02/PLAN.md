# Plan

Task: `P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02`

## Objective

Start the concrete repair loop for the 20 owner servers by adding an executable
repair-plan contract, generating per-node repair envelopes, and dispatching
repair tasks through the live Control Plane where possible.

## Scope

- Add a canonical 20 owner-server repair planner to `ops/factory_control.py`.
- Expose `GET /v1/fleet/repair-plan` for deployed Control Plane instances.
- Add `./ops/kolibri-dispatch repair-plan` so an operator or agent can print,
  write, and submit per-node repair envelopes.
- Generate one repair envelope per canonical owner server under this run.
- Submit those envelopes to the existing live `/v1/tasks` endpoint.

## Safety

- No secrets or credential values are printed.
- No destructive git commands are used.
- No force push or push to `main`.
- Repair envelopes require non-secret GitHub auth smoke checks and exact blocker
  commands when a node cannot be repaired safely.
- Production restarts remain gated by owner approval in the child envelopes.

