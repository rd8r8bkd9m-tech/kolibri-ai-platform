# Fleet Classification

Task: `P0_30MIN_FLEET_AGENT_ONLINE_ACCELERATION_WAVE_2026_07_02`

Source of truth for live capacity: `GET http://10.99.0.10:9101/v1/nodes`.

Initial timebox snapshot:

- Time: `2026-07-02T00:17:35Z`
- Visible node cards: `42`
- Online: `7`
- Stale: `35`
- Visible task states: `running=4`, `queued=229`, `completed=210`, `failed=144`, `dead_letter=32`, `cancelled=3`, `waiting_review=1`

Capacity snapshot during wave:

- Time: `2026-07-02T00:18:21Z` to `2026-07-02T00:19Z`
- Fresh online cards: `10`
- Stale cards: `32`
- Blocked cards in `/v1/nodes`: `0`

Final timebox snapshot:

- Time: `2026-07-02T00:48:16Z`
- Timebox end: `2026-07-02T00:48:23Z`
- Visible node cards: `42`
- Fresh online cards: `9`
- Stale cards: `33`
- Blocked cards in `/v1/nodes`: `0`
- Visible task states: `running=1`, `queued=225`, `completed=214`, `failed=146`, `dead_letter=33`, `cancelled=3`, `waiting_review=1`

Final fresh online runner-ready nodes:

| Node | Use |
|---|---|
| `main` | orchestration, implementation, review, Codex/MIMO runner tasks with low-memory caution |
| `mesh-9fts` | mesh implementation and MIMO runner work with explicit target |
| `mesh-agent-01` | implementation and runner work |
| `mesh-agent-02` | implementation and runner work; current task lease node |
| `mesh-agent-03` | implementation and runner work |
| `primary-candidate` | release-gate/control-standby runner work after final fresh heartbeat returned |

Final fresh online limited or role-specific nodes:

| Node | Use |
|---|---|
| `new` | review and read-only QA |
| `qjns` | read-only, review, QA, credential smoke only; no general implementation until GitHub/MIMO access is reclassified |
| `uiap` | RAG/knowledge/read-only work; avoid general implementation until runner credentials are verified |

Final stale cards:

`9fts`, `agent-01`, `agent-02`, `agent-03`, `agent-04`, `agent-05`, `agent-06`, `agent-07`, `agent-08`, `agent-09`, `highload`, `home`, `home-live`, `mesh-agent-04`, `mesh-agent-05`, `mesh-agent-06`, `mesh-agent-07`, `mesh-agent-08`, `mesh-agent-09`, `mesh-highload`, `mesh-home`, `mesh-main`, `mesh-new`, `mesh-paris`, `mesh-primary`, `mesh-qjns`, `mesh-reserve242`, `mesh-server-kfrm`, `mesh-uiap`, `paris`, `reserve242`, `server-kfrm`, `smoke-primary`.

Blocked/repair-required route entries:

- `/v1/nodes` reported no explicit blocked cards during the live capacity snapshot.
- `/v1/fleet/nodes` and `/v1/fabric/routes` reported `10` blocked/repair-required route entries. These endpoints are useful for repair planning but include broader route metadata than the freshness-aware capacity view.

Classification decision:

- Count only fresh `/v1/nodes` cards as restored always-online capacity.
- Do not count stale metadata or mesh shadow cards as capacity.
- Treat route-level blocked entries as repair backlog, not as online capacity.
- Final state is partial restoration: runner-ready capacity is available, but always-online fleet health is not fully restored while `33` stale cards remain.
