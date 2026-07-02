# PLAN

Objective: continue from PR #141 head `19e1932d426073cab7cbeae7d3b3d488b0d0fde4` and repair the strict canary failures below the JSON/logging layer.

Focus:

- Keep high-concurrency empty lease polls on `200/no_task` without transport status `0`.
- Keep canary task leasing at `created_tasks == leased_tasks` through 1000.
- Do not deploy or restart runtime from this implementation task.

Implementation plan:

1. Add a warmed-empty accept-loop fast path for valid ordinary `/v1/tasks/lease` POSTs so empty polls do not wait behind the capped HTTP worker executor.
2. Drain the complete request body before replying to avoid client-side connection resets.
3. Strengthen queued-task recovery so a bounded random index sample cannot miss the only compatible persisted queued task.
4. Add tests for 1000 concurrent leasing, 1000 warmed empty HTTP polls, and the accept-loop shortcut.
