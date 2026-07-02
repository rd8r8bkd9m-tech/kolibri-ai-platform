# Lease Storm Root Cause

The incident was an operational overload, not a single bad task.

Observed on `primary-candidate`:

- Control Plane was active in systemd but `/health` and `/v1/nodes` timed out.
- `/v1/tasks/lease` and `/v1/tasks` returned 500 responses.
- Logs contained `BrokenPipeError` and `OSError: [Errno 24] Too many open files`.
- The running process had soft `NOFILE=1024`.
- The process was near the fd limit with around 916 file descriptors.
- Thread count reached around 819.
- Around 102 Agent Host services were polling the lease endpoint.

Root cause:

1. Too many workers were polling a lease endpoint that was not designed as a cheap fast path.
2. Expired lease requeue work could run from the lease path instead of a bounded singleflight reaper.
3. Redis access used short-lived TCP sockets, increasing fd pressure.
4. Request handler concurrency was unbounded enough to grow thread pressure during slow/error responses.
5. Agent Host polling had insufficient backoff/jitter on unhealthy Control Plane responses.

Emergency mitigation:

- Increased Control Plane `LimitNOFILE` to 65536 and `TasksMax` to 4096.
- Reduced local Agent Host services from 102 to 21.
- Restored health, but this was defense-in-depth, not the permanent fix.
