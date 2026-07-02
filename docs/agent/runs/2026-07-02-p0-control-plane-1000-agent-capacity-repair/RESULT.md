# Result

Implemented capacity guards for 1000+ logical agents.

Capacity numbers from tests:

- 1200 queued logical tasks created in fake Redis.
- 1000 logical lease polls completed in-process.
- 1000 unique leases returned.
- 200 tasks remained queued.
- Queue acquisition used exactly 1000 `LPOP` operations for 1000 compatible polls.
- No OS processes were started by the capacity simulation.
- 1000 logical Agent Host instances produced more than 900 distinct idle sleep values, bounded between 1 and 15 seconds.
- Lease reaper was lock-gated and batch-limited to 10 changes in the focused test.
- Redis client reused 1 socket for 2 sequential commands on the same thread.

Operational defaults:

- `FACTORY_MAX_HTTP_WORKERS=64`
- `FACTORY_LEASE_QUEUE_SCAN_LIMIT=100`
- `FACTORY_LEASE_REAPER_BATCH_LIMIT=250`
- `FACTORY_LEASE_REAPER_INTERVAL=5`
- `FACTORY_TASK_LIST_DEFAULT_LIMIT=1000`
- `KOLIBRI_LEASE_IDLE_MIN=1.0`
- `KOLIBRI_LEASE_IDLE_MAX=15.0`
- `KOLIBRI_LEASE_EMPTY_BACKOFF_FACTOR=1.35`

Remote implementation location: server worktree under `/var/lib/kolibri-agent/worktrees/.../repo`; no Mac-local implementation was used.

