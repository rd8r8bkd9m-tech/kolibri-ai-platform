# ACTIONS

Actions performed from the server-side leased worker `mesh-agent-29:agent-host-mesh-agent-29`:

1. Queried exact parent task status with `python3 ops/kolibri-dispatch status P0_AUTOPILOT_EXTRA_29_HOSTVDS_AGENT_07_READINESS_2026_07_02`.
2. Queried Control Plane nodes with `python3 ops/kolibri-dispatch nodes` and filtered only `agent-07` / `mesh-agent-07`.
3. Checked Fabric route endpoint with `python3 ops/kolibri-dispatch fabric-route mesh-agent-07 --required-capability read_only_probe`.
4. Tried bounded non-interactive SSH alias probe for `hostvds-agent-07`; it timed out on port 22.
5. Created docs-only child envelope `docs/agent/dispatcher/envelopes/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02.json`.
6. Submitted child task through Control Plane with `python3 ops/kolibri-dispatch submit --file docs/agent/dispatcher/envelopes/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02.json`.
7. Polled exact child task `P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02`.

Important evidence:

- Parent lease owner: `mesh-agent-29:agent-host-mesh-agent-29`.
- Parent worktree: `/var/lib/kolibri-agent/logical-workers/mesh-agent-29/worktrees/P0_AUTOPILOT_EXTRA_29_HOSTVDS_AGENT_07_READINESS_2026_07_02/P0_AUTOPILOT_EXTRA_29_HOSTVDS_AGENT_07_READINESS_2026_07_02-attempt-1/repo`.
- Target node current card: `mesh-agent-07`, agent `agent-host-mesh-agent-07`, health `online`, fresh `true`.
- Stale alias card: `agent-07`, health `stale`, heartbeat from `2026-06-30T11:56:42Z`.
- Direct child probe lease owner: `mesh-agent-07:agent-host-mesh-agent-07`.
- Direct child probe artifact directory: `/var/lib/kolibri-agent/logical-workers/mesh-agent-07/artifacts/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02-attempt-1/`.

No raw auth output, env files, tokens, cookies, private keys, or credential helper output were printed into this artifact.
