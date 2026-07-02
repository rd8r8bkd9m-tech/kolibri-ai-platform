# EMPTY LEASE LATENCY CAUSE

Observed blocker:

- PR #140 preserved the 64-worker cap and removed accept-loop semaphore blocking.
- Live strict canary still failed empty-poll transport status at stages `250` and `500`.
- Threads stayed bounded at `65`, so the remaining issue was no longer worker growth.

Cause addressed by this stacked repair:

- The empty `/v1/tasks/lease` path still performed Redis queue/index checks for every empty poll.
- Under a burst of hundreds of empty polls and only 64 HTTP workers, repeated Redis work and JSON handling could keep workers occupied long enough for tail clients to time out.
- The runtime canary records those client timeouts as empty-poll `status 0`.

Repair:

- Add a short-lived in-process empty queue cache controlled by `FACTORY_LEASE_EMPTY_FAST_PATH_TTL`.
- Return warmed normal empty polls before Redis drain, reaper, node load, queue length, or queued-index checks.
- Invalidate the cache on queued task save and queue enqueue so task creation wakes the lease path.
- Preserve HTTP `200/no_task`, the 64-worker cap, and PR #140 non-blocking accept-loop behavior.
