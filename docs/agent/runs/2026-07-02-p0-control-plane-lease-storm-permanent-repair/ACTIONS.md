# Actions

- Relayed the remote `primary-candidate` implementation commit into branch `p0/control-plane-lease-storm-permanent-repair-2026-07-02`.
- Added per-thread persistent Redis connections with reconnect-on-error.
- Added bounded Control Plane request handler concurrency via `FACTORY_MAX_HTTP_WORKERS`.
- Replaced full queue materialization on lease with bounded `LPOP` queue scanning.
- Added Redis-backed reaper interval and singleflight lock behavior.
- Added Agent Host idle polling jitter and empty-poll backoff.
- Added task listing limits so `/v1/tasks?limit=N` remains bounded.
- Added capacity tests for reaper gating, 1000 logical lease polls, Redis socket reuse, and Agent Host backoff cadence.
