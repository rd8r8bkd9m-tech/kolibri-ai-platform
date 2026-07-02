# ACTIONS

- Confirmed this is not a local Mac implementation. The task is leased by Control Plane to `mesh-agent-02:agent-host-mesh-agent-02` with remote worktree under `/var/lib/kolibri-agent/logical-workers/mesh-agent-02/...`.
- Read the local dispatcher contract and always-online policy:
  - `docs/agent/AGENT_RUNNER_CONTRACT.md`
  - `docs/agent/dispatcher/README.md`
  - `docs/superfactory/FLEET_ALWAYS_ONLINE_POLICY.md`
  - `docs/agent/dispatcher/QUEUE.md`
- Queried exact task status with `ops/kolibri-dispatch status P0_30MIN_12AGENT_02_FLEET_ONLINE_STEWARD_2026_07_02`.
- Queried fleet node state with `ops/kolibri-dispatch nodes`.
- Queried the active queue with `ops/kolibri-dispatch status`; the result is truncated by Control Plane limits but still shows the queue is large and active.
- Created only docs run artifacts under the exact required path.

## Observed Control Plane Evidence

- Task state during work: `running`.
- Attempt: `P0_30MIN_12AGENT_02_FLEET_ONLINE_STEWARD_2026_07_02-attempt-1`.
- Lease owner: `mesh-agent-02:agent-host-mesh-agent-02`.
- Heartbeat observed during task: `2026-07-02T00:59:08.241774+00:00`.
- Node snapshot summary:
  - registered nodes: `42`;
  - canonical nodes: `18`;
  - fresh nodes: `8`;
  - fresh non-draining nodes: `8`;
  - fresh canonical nodes: `6`;
  - fresh canonical generic implementation nodes: `4`;
  - mesh shadow duplicate cards: `19`;
  - duplicate hostname groups: `3`.

## Working Capacity Snapshot

Fresh useful nodes observed:

| Node | Status | Notes |
| --- | --- | --- |
| `main` | online | Fresh, runner-capable, low RAM headroom. |
| `mesh-9fts` | online | Fresh but already running `P0_30MIN_12AGENT_09_SKILLS_REGISTRY_STEWARD_2026_07_02`; very low memory. |
| `mesh-agent-01` | online | Fresh and running `P0_30MIN_12AGENT_06_HOME_WALLBOARD_STEWARD_2026_07_02`. |
| `mesh-agent-02` | online | Fresh and running this task. |
| `mesh-agent-03` | online | Fresh and running `P0_30MIN_SECOND_WAVE_MESH_AGENT_03_AGENT_LAUNCH_GATE_2026_07_02`. |
| `new` | online | Fresh, review/read-only capable; no active task. |
| `qjns` | online | Fresh, light implementation/review capable; low RAM, known auth/provider blockers from prior queue. |
| `uiap` | online | Fresh RAG/research node; no active task, suitable for light knowledge tasks. |

Stale or degraded groups:

- Base canonical cards `9fts`, `agent-01` through `agent-09`, `highload`, `paris`, `reserve242`, and `server-kfrm` are stale by heartbeat.
- `home` and `home-live` have stale heartbeats around 30 minutes and must not be counted as fresh.
- `primary-candidate` is carrying an active release task but its heartbeat is stale in the observed snapshot.
- Mesh shadow cards for many base nodes are stale and duplicate canonical identities; they are metadata debt until refreshed or reconciled.

No product code was changed. No secrets were printed. No Git push was attempted.
