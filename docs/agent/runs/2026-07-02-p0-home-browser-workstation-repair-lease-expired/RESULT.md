# Result

Status: `lease_expired_dead_letter_repair`

Task id: `P0_HOME_BROWSER_WORKSTATION_REPAIR_2026_07_02`

Control Plane status:

- Error type: `lease_expired`.
- Error: `lease expired and retry budget exhausted`.
- Terminal state: `dead_letter`.

Classification:

- The task failed because the agent lease expired before the task could complete
  and the retry budget (`max_retries`) was exhausted.
- The Control Plane moved the task to `dead_letter` state via
  `requeue_expired_leases()` in `ops/factory_control.py:746`.
- This is an **automatically repairable** failure. No operator/manual
  intervention is required for the lease mechanism itself.

Root cause pattern:

- Agent Host was unable to complete the task within the lease window
  (default 60 seconds, `FACTORY_LEASE_DURATION`).
- Agent Host could not post heartbeat/fail while the target service
  was down (e.g., `Connection refused` when Factory Control restarted).
- The retry budget was set too low or the task workload exceeded the
  available lease time.

Repair action implemented:

- Added `GET /v1/tasks/dead-letter` endpoint to inspect all dead letter tasks.
- Added `POST /v1/tasks/{task_id}/rerun` endpoint to re-queue dead letter tasks
  with a fresh attempt counter and cleared lease state.
- Both endpoints return canonical Fabric API response envelopes with
  `repair_task` and `next_action` fields.

Rerun path through Fabric API:

1. Inspect dead letter: `GET /v1/tasks/dead-letter`
2. Rerun target task: `POST /v1/tasks/{task_id}/rerun`
3. Monitor status: `GET /v1/agents/status/{task_id}`
4. Collect artifacts: `GET /v1/agents/artifacts/{task_id}`

Or via CLI:

```bash
ops/kolibri-dispatch status P0_HOME_BROWSER_WORKSTATION_REPAIR_2026_07_02
```

If the task is still in `dead_letter` state in the live Control Plane, submit a
new task envelope through `POST /v1/tasks` or `POST /v1/agents/tasks` with the
same objective and increased `max_retries` and/or `FACTORY_LEASE_DURATION`.
