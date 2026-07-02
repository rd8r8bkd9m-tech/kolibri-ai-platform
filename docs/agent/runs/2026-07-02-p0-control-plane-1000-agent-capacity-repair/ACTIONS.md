# Actions

- Added per-thread persistent Redis connections with reconnect-on-error in `ops/factory_control.py`.
- Added `BoundedThreadingHTTPServer` with `FACTORY_MAX_HTTP_WORKERS` to prevent unbounded request-handler thread creation during lease bursts.
- Replaced full queue materialization during lease with bounded `LPOP`-based scanning controlled by `FACTORY_LEASE_QUEUE_SCAN_LIMIT`.
- Added Redis `SET NX EX` lease reaper gating plus `FACTORY_LEASE_REAPER_BATCH_LIMIT`.
- Added task list pagination defaults to keep `/v1/tasks` bounded.
- Added Agent Host idle polling jitter and exponential empty-poll backoff controlled by `KOLIBRI_LEASE_IDLE_*` settings.
- Added capacity tests covering 1000 logical lease polls, reaper gating, Redis socket reuse, and 1000 jittered logical host cadences.

