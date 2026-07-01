# P0 PR85 Prompt 3 Fabric API Surface Repair

Task: `P0_PR85_PROMPT3_FABRIC_API_SURFACE_REPAIR_2026_07_01`

Node: `kolibri`

Agent display name: `Сергей — Fabric API Engineer`

Branch: `p0/api-first-full-control-fabric-2026-07-01`

Base HEAD before repair commits: `9690361f02addeff37771c52fd37878aef455e13`

Scope:

- Implemented Prompt #3 required server-side Fabric API endpoint surface in `ops/factory_control.py`.
- Added safe deny-by-default stubs for model generation and privileged admin actions.
- Added aliases for fleet, agents, status, artifacts and cancellation.
- Added tests for aliases, stubs, canonical envelopes and fallback reason taxonomy.
