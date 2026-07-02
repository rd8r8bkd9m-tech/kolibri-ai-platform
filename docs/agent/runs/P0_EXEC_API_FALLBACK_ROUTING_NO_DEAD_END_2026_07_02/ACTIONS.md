# Actions

- Confirmed worktree branch: `agent/P0_EXEC_API_FALLBACK_ROUTING_NO_DEAD_END_2026_07_02/generic`.
- Extended the canonical Fabric API response envelope with fallback route metadata:
  - `fallback_route`
  - `can_continue_elsewhere`
- Added `route_target_from_envelope` to normalize `auto`, empty, and wildcard targets as non-specific routes.
- Added `blocked_agent_task_route` to classify `/v1/agents/tasks` dispatchability before queue insertion.
- Added `blocked_agent_task_route_envelope` to map route failures into canonical blocked responses.
- Updated `/v1/agents/tasks` so unavailable or unroutable target/capability requests return HTTP 503 with structured fallback and repair metadata instead of creating an unleaseable queued task.
- Added regression tests for:
  - unavailable target node with a fallback candidate;
  - required capability with no matching route.

