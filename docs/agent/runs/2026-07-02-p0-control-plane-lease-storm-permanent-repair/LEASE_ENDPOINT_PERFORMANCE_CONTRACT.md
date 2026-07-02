# Lease Endpoint Performance Contract

`/v1/tasks/lease` is a fast path.

Contract:

- Parse one request.
- Optionally call the throttled reaper gate.
- Check drain state for the node.
- Lease at most one task.
- Return `204` when no compatible task is available.
- Avoid full queue serialization.
- Avoid full task list serialization.
- Avoid per-command socket churn.
- Bound queue scanning via `FACTORY_LEASE_QUEUE_SCAN_LIMIT`.

The endpoint must remain responsive when many logical agents poll.

Expected overload behavior:

- No tight 500 loops for ordinary empty queue or incompatible tasks.
- No unbounded request-handler thread growth.
- No full Redis keyspace or queue scan per poll.
- Structured diagnostics should make overload visible without printing secrets.
