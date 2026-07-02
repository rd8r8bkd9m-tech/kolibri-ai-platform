# Plan

Task: `P0_EXEC_API_FALLBACK_ROUTING_NO_DEAD_END_2026_07_02`

1. Inspect the existing Fabric API route and task submission contracts.
2. Identify the dead-end path where `/v1/agents/tasks` can enqueue work for an unavailable target node.
3. Add a reusable route classification helper that does not require Redis so it can be unit-tested directly.
4. Return a canonical blocked response with `route_used`, `fallback_nodes`, `fallback_route`, `can_continue_elsewhere`, `repair_task`, and `next_action` before enqueueing unrouteable agent work.
5. Add regression tests for unavailable target and missing-capability routing.
6. Run focused and adjacent factory-control tests.

