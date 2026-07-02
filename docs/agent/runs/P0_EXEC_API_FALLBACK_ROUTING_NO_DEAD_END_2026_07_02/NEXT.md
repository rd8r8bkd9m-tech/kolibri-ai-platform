# Next

Exact next task:

Deploy this branch to a scoped factory-control canary and exercise live HTTP requests:

```text
POST /v1/agents/tasks
```

Canary cases:

- `target_node=9fts`, `required_capability=generic_implementation`, with `9fts` offline and `new` online.
- `required_capability=unique_gpu_runtime`, with no matching online node.
- `target_node=auto`, to confirm generic queue submission still works.

Expected result:

- Unavailable explicit target returns structured `blocked` with fallback metadata and no queued task.
- Missing unique capability returns structured `blocked` with `can_continue_elsewhere=false`.
- Auto target still creates a normal running task envelope.

