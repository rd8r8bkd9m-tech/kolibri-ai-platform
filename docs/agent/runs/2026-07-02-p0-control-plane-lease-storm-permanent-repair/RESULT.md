# Result

Status: code PR prepared, not deployed.

Root cause summary:

- `primary-candidate` had around 102 Agent Host services polling `/v1/tasks/lease`.
- The previous lease path ran expensive expired-lease requeue work too often.
- The stdlib Redis helper opened a new TCP socket per command.
- `ThreadingHTTPServer` could create too many request-handler threads under pressure.
- The runtime process had soft `NOFILE=1024`, with around 916 file descriptors and around 819 threads observed during the incident.
- The combined effect produced health timeouts, task endpoint 500s, BrokenPipe loops, and `OSError: [Errno 24] Too many open files`.

Behavior implemented:

- Redis client now reuses one persistent socket per thread and reconnects on error.
- Lease reaper is throttled and protected by a Redis singleflight lock.
- Reaper work is batch limited.
- Lease acquisition uses bounded `LPOP` scanning instead of full queue materialization.
- HTTP request handler concurrency is bounded by `FACTORY_MAX_HTTP_WORKERS`.
- `/v1/tasks` has bounded default/max limits.
- Agent Host idle polling now uses deterministic jitter and exponential empty-poll backoff.

Capacity evidence:

- 1200 queued logical tasks simulated.
- 1000 logical lease polls completed in-process.
- 1000 unique leases returned.
- 200 tasks remained queued.
- Exactly 1000 `LPOP` operations for 1000 compatible polls.
- 1000 logical Agent Host cadences produced more than 900 distinct sleep values, bounded between 1 and 15 seconds.
- Redis client reused 1 socket for 2 sequential commands on the same thread.

Runtime deployment status:

- Not deployed in this task.
- Emergency production mitigation remains active on `primary-candidate`: `LimitNOFILE=65536`, `TasksMax=4096`, and 21 running Agent Host services.

PR #119 release gate:

- Do not retry PR #119 release gate yet.
- Retry only after `P0_CONTROL_PLANE_LEASE_STORM_RUNTIME_CANARY_2026_07_02` deploys this repair and proves fd/thread/latency stability under staged polling pressure.
