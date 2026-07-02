# Plan

Task: `P0_CONTROL_PLANE_RUNNER_ROUTE_COMPATIBILITY_REPAIR_2026_07_02`

Goal: stop the Control Plane from leasing AI-runner tasks to nodes that cannot
execute the requested runner, and keep MIMO Pool bootstrap pinned to its backing
node.

## Plan

1. Inspect recent failed director tasks and lease-routing code.
2. Add an effective runner contract in Control Plane compatibility checks.
3. Treat implicit `owner_remote_task` as requiring the default MIMO runner, to
   match Agent Host execution behavior.
4. Preserve explicit runner requirements such as `runner=codex`.
5. Preserve `target_node`, `avoid_nodes`, `allowed_nodes` and
   `required_capability`.
6. Add focused tests for runner gating and MIMO Pool target routing.

