# Actions

Executed from server-side Control Plane lease worktree:

- Current worker path: `/var/lib/kolibri-agent/logical-workers/mesh-agent-23/worktrees/P0_AUTOPILOT_EXTRA_23_HOSTVDS_AGENT_01_READINESS_2026_07_02/P0_AUTOPILOT_EXTRA_23_HOSTVDS_AGENT_01_READINESS_2026_07_02-attempt-1/repo`
- Current hostname: `kolibri`
- Current branch: `agent/P0_AUTOPILOT_EXTRA_23_HOSTVDS_AGENT_01_READINESS_2026_07_02/generic`

Commands/actions:

- Read dispatcher and Agent Host contracts.
- Queried Control Plane node registry with `python3 ops/kolibri-dispatch nodes`.
- Added dispatcher envelope:
  - `docs/agent/dispatcher/envelopes/P0_AUTOPILOT_EXTRA_23_HOSTVDS_AGENT_01_READINESS_2026_07_02.json`
- Submitted exact task through Control Plane:
  - `python3 ops/kolibri-dispatch submit --file docs/agent/dispatcher/envelopes/P0_AUTOPILOT_EXTRA_23_HOSTVDS_AGENT_01_READINESS_2026_07_02.json`
- Polled exact task:
  - `python3 ops/kolibri-dispatch status P0_AUTOPILOT_EXTRA_23_HOSTVDS_AGENT_01_READINESS_2026_07_02`
- Rechecked node cards for `agent-01`, `mesh-agent-01`, and `mesh-agent-23`.

Observed routing:

- Envelope target was `mesh-agent-01`.
- Envelope `allowed_nodes` was only `mesh-agent-01`.
- Running task worktree/log paths are under `logical-workers/mesh-agent-23`.
- Node card shows `mesh-agent-23` active on this task.
- Node card shows `mesh-agent-01` online, fresh, and idle.
