# Task Routing Contract

Routing order:

1. Exact target if healthy, fresh, not draining and capable.
2. Canonical alias match.
3. Explicit `allowed_nodes` fallback if present.
4. Capability-compatible fallback only when policy allows.
5. Structured blocked response with repair task.

## Required Diagnostics

Queue diagnostics must explain:

- `leaseable`
- `target_mismatch`
- `node_not_allowed`
- `missing_capability`
- `missing_runner_capability`
- `runner_blocked`
- `node_draining`
- `node_stale`
- `node_degraded`
- `node_offline`
- `task_not_queued`
- `no_matching_node`

The dispatcher must not bypass `allowed_nodes` silently.

