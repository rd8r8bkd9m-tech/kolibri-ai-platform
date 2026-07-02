# PR119 Unblock After Permanent Repair

Current decision:

`PR #119 release gate remains blocked until this repair is deployed and canaried.`

Reason:

- PR #119 fixes long-running lease heartbeat behavior, but the release gate was blocked by Control Plane lease-storm instability.
- Deploying PR #119 canary before the lease endpoint is stable could re-create the same overload condition.

Unblock criteria:

- This branch is merged or deployed to the target runtime under canary.
- `/v1/health` remains responsive during staged lease polling.
- `/v1/tasks/lease` does not produce 500/BrokenPipe loops.
- fd and thread counts remain bounded through the 1000 logical-agent stage.
- Agent Host backoff/jitter is active.
- Rollback path is documented.

Next exact task after merge/PR readiness:

`P0_CONTROL_PLANE_LEASE_STORM_RUNTIME_CANARY_2026_07_02`
