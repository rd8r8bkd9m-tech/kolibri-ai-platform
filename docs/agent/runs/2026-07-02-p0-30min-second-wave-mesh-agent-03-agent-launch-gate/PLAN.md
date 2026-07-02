# Plan

Task id: `P0_30MIN_SECOND_WAVE_MESH_AGENT_03_AGENT_LAUNCH_GATE_2026_07_02`

Node: `mesh-agent-03`

Goal: run the second 30-minute remote-agent launch gate without unsafe fanout,
provider limit bypass, fake accounts, secret disclosure, destructive commands or
production service changes.

## Gate Steps

1. Confirm this worktree is running under the `mesh-agent-03` Control Plane
   lease.
2. Snapshot Control Plane health, node freshness and current queue pressure.
3. Read the durable always-online and fleet-role policies.
4. Classify safe launch targets from fresh evidence only.
5. Produce a bounded second-wave launch plan that routes work only through
   Control Plane task envelopes with idempotency keys, explicit write scopes,
   artifact outputs and retry limits.
6. Do not spawn uncontrolled local processes, do not start or restart services,
   do not create accounts, and do not touch provider credentials.
7. Verify exact artifacts and markdown formatting.

## Source Of Truth

- `docs/superfactory/FLEET_ALWAYS_ONLINE_POLICY.md`
- `docs/agent/dispatcher/OWNER_CANONICAL_INSTRUCTIONS.md`
- `docs/agent/intelligence/2026-07-01-fleet-role-capability-inventory/FLEET_ROLE_MATRIX.md`
- `docs/agent/intelligence/2026-07-01-fleet-role-capability-inventory/TARGET_POOLS.md`
- live `ops/kolibri-dispatch doctor`
- live `ops/kolibri-dispatch nodes`
- live task status for this task id

## Launch Policy

Second-wave launch is approved only as a small, capacity-gated control-plane
wave. The gate explicitly rejects old queued MIMO fanout against stale
`mesh-agent-04..09`, `mesh-highload`, `mesh-paris`, `mesh-reserve242`, and
`mesh-server-kfrm` cards until fresh Agent Host heartbeats and runner/resource
evidence are restored.
