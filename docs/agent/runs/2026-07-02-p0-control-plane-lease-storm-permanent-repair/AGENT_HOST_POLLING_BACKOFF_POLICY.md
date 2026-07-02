# Agent Host Polling Backoff Policy

Agent Host must not hammer Control Plane when the lease endpoint is empty or unhealthy.

Implemented policy:

- Deterministic per-agent jitter seeded from `agent_id`.
- Empty-poll backoff between `KOLIBRI_LEASE_IDLE_MIN` and `KOLIBRI_LEASE_IDLE_MAX`.
- Backoff factor controlled by `KOLIBRI_LEASE_EMPTY_BACKOFF_FACTOR`.
- Error backoff controlled by `KOLIBRI_LEASE_ERROR_BACKOFF`.
- `max_inflight` is clamped to at least 1.

Default values:

- `KOLIBRI_LEASE_IDLE_MIN=1.0`
- `KOLIBRI_LEASE_IDLE_MAX=15.0`
- `KOLIBRI_LEASE_EMPTY_BACKOFF_FACTOR=1.35`
- `KOLIBRI_LEASE_ERROR_BACKOFF=5.0`

Effect:

- 1000 logical Agent Host cadences do not align into a thundering herd.
- Empty queues produce slower polling.
- Error paths pause instead of immediately retrying.
