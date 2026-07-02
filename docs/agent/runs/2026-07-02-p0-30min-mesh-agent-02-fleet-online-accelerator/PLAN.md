# Plan

Task id: `P0_30MIN_MESH_AGENT_02_FLEET_ONLINE_ACCELERATOR_2026_07_02`

Node: `mesh-agent-02`

Goal: accelerate fleet online restoration with a reusable Control Plane
contract that reports canonical fleet health, safe fallback capacity, stale
metadata debt, and idempotent repair backlog.

Steps:

1. Inspect existing fleet policy, dispatcher queue, Control Plane routing, and
   tests.
2. Add a pure `fleet_guardian_snapshot` helper for the canonical 20-server
   restoration view.
3. Expose the snapshot through a safe read endpoint.
4. Add focused regression tests for fresh capacity, stale cards, unreachable
   servers, fallback nodes, and repair tasks.
5. Run compile and focused pytest verification.

