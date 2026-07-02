# RESULT

Status: implementation complete locally on stacked branch `codex/pr140-empty-lease-latency-repair`.

PR #140 still let strict live canary fail at stages 250 and 500 with empty-poll status `0` because the nominal empty fast path still performed Redis work on every request. Under 250/500 simultaneous empty polls, that kept the 64 worker threads busy with repeated drain, queue length, and queued-index checks.

This repair adds a deeper empty no-task fast path:

- A confirmed empty queue is cached briefly in-process with `FACTORY_LEASE_EMPTY_FAST_PATH_TTL`, default `0.25` seconds.
- Warmed normal empty lease polls return `200/no_task` before Redis drain, reaper, node load, or queue/index checks.
- The cache is invalidated when a task is saved as queued/review or when a task id is enqueued.
- PR #140's 64-worker cap remains intact.
- The accept loop still submits without semaphore blocking.

Expected next gate: stacked PR or branch relay, CI, then owner-approved runtime deploy and strict canary rerun. Runtime deploy was intentionally not performed here.
