# Control Plane Reaper Design

The lease reaper must not run once per `/v1/tasks/lease` request.

Policy:

- Reaper runs only when the interval says it is due.
- Only one reaper runs per Control Plane instance/window.
- Reaper work is batch limited.
- Reaper errors are counted/classified and do not turn every lease poll into an outage.

Environment knobs:

- `FACTORY_LEASE_REAPER_INTERVAL`
- `FACTORY_LEASE_REAPER_LOCK_TTL`
- `FACTORY_LEASE_REAPER_BATCH_LIMIT`

Expected behavior:

- If the reaper is not due, the lease path skips it.
- If another reaper holds the lock, the lease path skips reaper work and continues.
- If the reaper fails, the system records the error and keeps the health endpoint cheap.

This turns lease cleanup into periodic bounded maintenance instead of request-amplified global work.
