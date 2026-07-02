# Result

Status: `working_safe_route_with_legacy_path_blocker`

Task id: `P0_EXEC_CANCELLED_HOSTVDS_AGENT_02_REPAIR_2026_07_02`

Outcome:

- The stale/cancelled HostVDS path is explained.
- The safe route is identified and currently working through `mesh-agent-02`.
- A remaining live Fabric route deployment blocker is recorded with exact repair task.

What now works:

- `mesh-agent-02` is fresh/online in the Control Plane node card.
- `mesh-agent-02` maps to the legacy `agent-02` identity through `mesh_source_node_id=agent-02`.
- `mesh-agent-02` advertises factory execution capabilities including `implementation`, `generic_implementation`, `remote_implementation_runner_ready`, `runner:codex`, and `runner:mimo`.
- `mesh-agent-02` has a running task now:
  - Task: `P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02`
  - State: `running`
  - Lease owner: `mesh-agent-02:agent-host-mesh-agent-02`
  - Worktree: `/var/lib/kolibri-agent/logical-workers/mesh-agent-02/worktrees/P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02/P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02-attempt-1/repo`

Why the prior path was cancelled or ineffective:

- The legacy `agent-02` Control Plane card is stale, with heartbeat from `2026-06-30T11:56:41.610287+00:00`.
- Older tasks hard-targeted to `agent-02` remained queued with no lease.
- The prior HostVDS agent-02 readiness task, `P0_AUTOPILOT_EXTRA_24_HOSTVDS_AGENT_02_READINESS_2026_07_02`, recorded `cancel_requested_at=2026-07-02T02:58:05.437100+00:00`.
- That readiness task result says the intended `mesh-agent-02` probe was misrouted to `mesh-agent-24`, then cancelled to avoid wrong-node concurrent writes.
- Therefore the broken path was not a HostVDS capacity problem; it was stale identity plus scheduler/route targeting mismatch.

Safe route used:

- Use `mesh-agent-02`, not `agent-02` or `hostvds-agent-02`, for API-first factory work.
- Exact proof command:

```bash
python3 ops/kolibri-dispatch status P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02
```

Remaining blockers:

- Live `/v1/fabric/route` and `/v1/fabric/routes` queried from this worker returned HTTP `404`, even though the checked-in source documents and implements those contracts. This indicates the live listener reached by `http://10.99.0.2:9101` is not exposing the expected Fabric route surface from this route.
- Legacy `agent-02` metadata remains stale and should not be targeted directly.
- Old `target_node=agent-02` queued tasks remain in the task list and need retention/cancel cleanup after owner approval.
- GitHub auth on `mesh-agent-02` was not rechecked by this task because there is already a live running task on that node and no secret-printing or interactive auth is allowed.

Artifact paths:

- This run: `docs/agent/runs/P0_EXEC_CANCELLED_HOSTVDS_AGENT_02_REPAIR_2026_07_02/`
- Follow-up repair envelope: `docs/agent/dispatcher/envelopes/P0_REPAIR_HOSTVDS_AGENT_02_TARGETED_LEASE_AND_FABRIC_ROUTE_2026_07_02.json`
- Prior readiness result: `/var/lib/kolibri-agent/logical-workers/mesh-agent-24/artifacts/P0_AUTOPILOT_EXTRA_24_HOSTVDS_AGENT_02_READINESS_2026_07_02/P0_AUTOPILOT_EXTRA_24_HOSTVDS_AGENT_02_READINESS_2026_07_02-attempt-1/result.json`
- Current safe-route stdout: `/var/lib/kolibri-agent/logical-workers/mesh-agent-02/artifacts/P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02/P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02-attempt-1/stdout.log`
- This task logs:
  - `/var/lib/kolibri-agent/logical-workers/mesh-agent-14/artifacts/P0_EXEC_CANCELLED_HOSTVDS_AGENT_02_REPAIR_2026_07_02/P0_EXEC_CANCELLED_HOSTVDS_AGENT_02_REPAIR_2026_07_02-attempt-1/stdout.log`
  - `/var/lib/kolibri-agent/logical-workers/mesh-agent-14/artifacts/P0_EXEC_CANCELLED_HOSTVDS_AGENT_02_REPAIR_2026_07_02/P0_EXEC_CANCELLED_HOSTVDS_AGENT_02_REPAIR_2026_07_02-attempt-1/stderr.log`

Repair classification:

- No code change was made in this task.
- No server config was changed.
- No PR branch was pushed by this task.
- This task produces a working node status plus a hard blocker for the missing live Fabric route surface.

Next exact task:

`P0_REPAIR_HOSTVDS_AGENT_02_TARGETED_LEASE_AND_FABRIC_ROUTE_2026_07_02`

Exact repair command:

```bash
python3 ops/kolibri-dispatch submit --file docs/agent/dispatcher/envelopes/P0_REPAIR_HOSTVDS_AGENT_02_TARGETED_LEASE_AND_FABRIC_ROUTE_2026_07_02.json
```

The repair envelope should deploy or restart only the scoped Factory Control listener if preflight proves `/opt/kolibri-ai-platform/ops/factory_control.py` contains `/v1/fabric/routes` and `/v1/fabric/route`, then rerun a redacted exact `mesh-agent-02` lease probe.
