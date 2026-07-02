# Canonical 20-Server Readiness Matrix

Task: `P0_CANONICAL_20_SERVER_READINESS_MATRIX_2026_07_02`
Generated: `2026-07-02T02:45:00Z`
Lease owner: `autonomous_engineer`
Execution host: `kolibri` Linux Agent Host worktree, not Mac.
Control Plane evidence: `GET http://10.99.0.10:9101/v1/health` returned `status=completed`, `node=main`, `redis=PONG`, `queue_backend=redis`, `fabric_api_version=2026-07-01`.
Git evidence: `git ls-remote --heads origin main` returned `f7ac32c70406432a52752ca45d87e35d9f1facd3`.
Runner evidence on this Agent Host: `codex` and `mimo` binaries are present. Provider/auth execution was not smoke-tested by this read-only matrix task.

## Classification Rules

- `ready`: fresh Control Plane heartbeat, usable Agent Host route, resources present, and at least one safe 50 percent slot remains for the node role.
- `partial`: online but constrained by specialization, low memory, active-task pressure, missing runner capability, duplicate route ambiguity, or auth not fully smoke-tested.
- `repair`: route exists but heartbeat/resource/capability evidence is stale, degraded, missing, or contradictory enough to require a repair task before assignment.
- `offline-route`: no current Agent Host route; only fallback relay, stale metadata, or degraded mesh evidence exists.

Safe slots are conservative read-only estimates: `floor(vCPU * 0.5)` for nodes with live CPU data, with `0` for 1-vCPU general runners unless explicitly limited to a narrow probe. Occupied slots count active Control Plane task evidence visible in the node card.

## Matrix

| Server | Class | Role | Resources | Agent Host route | GitHub clone/fetch | Codex/MIMO/API readiness | Control Plane heartbeat | Safe 50% slots | Blockers | Next repair task |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |
| `home` | `partial` | command gateway, home orchestrator, standby control, network convergence | `plastilin`, 6 vCPU, 13.1/15.5 GiB RAM, 25.8/97.9 GiB disk free | `agent-host-home`; duplicate `home-live` also on `plastilin` | fetch proven only from current Agent Host; node advertises `git_push` permission but node-local fetch not smoke-tested | API route present; no explicit `runner:codex` or `runner:mimo`; `home-live` has Telegram capability | `home` ~139s stale by freshness gate; `home-live` ~35s degraded/fresh-adjacent | 2 | duplicate home cards; owner-facing route should not be used for broad work until heartbeat freshness is stable | Merge `home`/`home-live` identity or pick canonical owner gateway; verify heartbeat <=30s and run node-local read-only git/provider smoke |
| `main` | `partial` | control plane, orchestrator, implementation/review runner | `kolibri-main-api`, 1 vCPU, 0.6/1.9 GiB RAM, 6.7/18.7 GiB disk free | `agent-host-main` | fetch proven from current Agent Host; node advertises git/review permissions | `runner:codex`, `runner:mimo`, Fabric/control/artifact API; low RAM blocks heavy work | fresh, ~7s | 0 | low memory; use only bounded orchestration/review/probe work | Add memory guard to scheduler and keep `main` for control-plane probes until RAM pressure is relieved |
| `uiap` | `partial` | knowledge/RAG/research/security | `kolibri-rag-knowledge`, 2 vCPU, 1.8/3.8 GiB RAM, 12.4/37.5 GiB disk free | `agent-host-uiap` | fetch proven only from current Agent Host; node-local GitHub not smoke-tested | API route present; specialized RAG capabilities; no `runner:codex`/`runner:mimo` | fresh, ~3s | 1 | specialized node; general implementation runner not advertised | Run explicit RAG-only readiness and separate GitHub/provider smoke before general scheduling |
| `qjns` | `partial` | remote agent, QA/review/implementation | `kolibri-tools-executor`, 1 vCPU, 0.6/1.9 GiB RAM, 4.5/18.7 GiB disk free | `agent-host-qjns` | fetch proven only from current Agent Host; node advertises git permissions | Agent Host API present; capabilities include QA/review but no `runner:codex`/`runner:mimo` | fresh, ~11s | 0 | low memory; prior GitHub/MIMO credential blocker is not cleared by node-local smoke in this task | Run qjns credential smoke: runner binary, read-only GitHub auth, MIMO/Codex auth, disposable branch push if authorized |
| `9fts` | `partial` | implementation/model recovery node | `kolibri-inference-recovery`, 1 vCPU, 0.3/1.9 GiB RAM, 9.8/18.7 GiB disk free on live mesh card | `agent-host-mesh-9fts`; stale metadata card `9fts` also exists | fetch proven only from current Agent Host; node-local GitHub not smoke-tested | live mesh card has `runner:mimo`; no `runner:codex`; low RAM | live mesh fresh, ~7s; metadata card stale >38h | 0 | stale duplicate metadata; very low memory; MIMO-only runner evidence | Retire stale `9fts` metadata card and reserve live mesh route for narrow inference/MIMO recovery probes |
| `new` | `ready` | review agent | `kolibri-worker-backup`, 2 vCPU, 5.5/7.8 GiB RAM, 47.8/75.2 GiB disk free | `agent-host-new` | fetch proven only from current Agent Host; node-local GitHub not smoke-tested | Agent Host API and review capability; no model runner advertised | fresh, ~1s | 1 | review-only specialization; no `runner:*` | Add node-local read-only GitHub review smoke; keep as review/QA target |
| `primary` | `repair` | primary candidate, standby control, orchestration, implementation/review | `kolibri`, 8 vCPU, 9.4/11.7 GiB RAM, 49.1/98.3 GiB disk free | `agent-host-primary` as `primary-candidate`; mesh shadow `mesh-primary` exists | fetch proven only from current Agent Host; node advertises git permissions | `runner:codex`, `runner:mimo`; active task present | stale by freshness gate, ~7m51s at sample; active task `P0_30MIN_12AGENT_07B_QJNS_READINESS_FALLBACK_NO_CLONE_2026_07_02` | 3 | heartbeat stale despite strong capabilities; active task; naming mismatch `primary` vs `primary-candidate` | Repair primary heartbeat freshness and normalize `primary`/`primary-candidate` identity before new leases |
| `agent-01` | `ready` | mesh implementation runner | `kolibri`, 8 vCPU, 8.8/11.7 GiB RAM, 49.1/98.3 GiB disk free | `agent-host-mesh-agent-01` | current task Agent Host has working fetch; node advertises git permissions | `runner:codex`, `runner:mimo`, Fabric relay; currently running this matrix task | fresh, ~5s | 3 | one occupied slot; shared physical host with other mesh agents | After this task, keep within shared-host 50 percent cap and avoid overcommitting all `kolibri` mesh agents |
| `agent-02` | `ready` | mesh implementation runner | `kolibri`, 8 vCPU, 8.8/11.7 GiB RAM, 49.1/98.3 GiB disk free | `agent-host-mesh-agent-02` | fetch proven only from current Agent Host; node advertises git permissions | `runner:codex`, `runner:mimo`, Fabric relay | fresh, ~5s | 3 | active task `P0_FLEET_CAPACITY_GOVERNOR_50PCT_2026_07_02`; shared physical host | Respect capacity governor result; schedule only if shared-host slot budget remains |
| `agent-03` | `ready` | mesh implementation runner | `kolibri`, 8 vCPU, 8.8/11.7 GiB RAM, 49.1/98.3 GiB disk free | `agent-host-mesh-agent-03` | fetch proven only from current Agent Host; node advertises git permissions | `runner:codex`, `runner:mimo`, Fabric relay | fresh, ~6s | 3 | active task `P0_HOME_WALLBOARD_AUTOPILOT_VISIBILITY_2026_07_02`; shared physical host | Wait for active UI task to settle before assigning heavy tests |
| `agent-04` | `ready` | mesh implementation runner | `kolibri`, 8 vCPU, 8.8/11.7 GiB RAM, 49.1/98.3 GiB disk free | `agent-host-mesh-agent-04` | fetch proven only from current Agent Host; node advertises git permissions | `runner:codex`, `runner:mimo`, Fabric relay | fresh, ~5s | 3 | active task `P0_QUEUE_GUARDIAN_REQUEUE_AND_DEADLETTER_POLICY_2026_07_02`; shared physical host | Keep queue-guardian work isolated; no broad fanout until queue policy task finishes |
| `agent-05` | `ready` | mesh implementation runner | `kolibri`, 8 vCPU, 8.8/11.7 GiB RAM, 49.1/98.3 GiB disk free | `agent-host-mesh-agent-05` | fetch proven only from current Agent Host; node advertises git permissions | `runner:codex`, `runner:mimo`, Fabric relay | fresh, ~5s | 3 | active task `P0_GITHUB_RELEASE_TRAIN_AUTOPILOT_STEWARD_2026_07_02`; shared physical host | Avoid overlapping GitHub release automation with other GitHub-mutating work |
| `agent-06` | `ready` | mesh implementation runner | `kolibri`, 8 vCPU, 8.8/11.7 GiB RAM, 49.1/98.3 GiB disk free | `agent-host-mesh-agent-06` | fetch proven only from current Agent Host; node advertises git permissions | `runner:codex`, `runner:mimo`, Fabric relay | fresh, ~5s | 3 | active task `P0_AGENT_HOST_RUNNER_CONTRACT_AUTOPILOT_GATE_2026_07_02`; shared physical host | Let runner-contract gate finish before assigning provider-auth repairs |
| `agent-07` | `ready` | mesh implementation/docs runner | `kolibri`, 8 vCPU, 8.8/11.7 GiB RAM, 49.1/98.3 GiB disk free | `agent-host-mesh-agent-07` | fetch proven only from current Agent Host; node advertises git permissions | `runner:codex`, `runner:mimo`, Fabric relay | fresh, ~6s | 3 | active task `P1_SKILLS_REGISTRY_AND_TEAM_HANDOFF_MESH_2026_07_02`; shared physical host | Keep as docs/registry slot; avoid heavy builds until active task completes |
| `agent-08` | `ready` | mesh implementation runner | `kolibri`, 8 vCPU, 8.8/11.7 GiB RAM, 49.1/98.3 GiB disk free | `agent-host-mesh-agent-08` | fetch proven only from current Agent Host; node advertises git permissions | `runner:codex`, `runner:mimo`, Fabric relay | fresh, ~8s | 4 | shared physical host with other active mesh agents | Best immediate free implementation slot if shared-host governor allows |
| `agent-09` | `ready` | mesh implementation runner | `kolibri`, 8 vCPU, 8.8/11.7 GiB RAM, 49.1/98.3 GiB disk free | `agent-host-mesh-agent-09` | fetch proven only from current Agent Host; node advertises git permissions | `runner:codex`, `runner:mimo`, Fabric relay | fresh, ~8s | 4 | shared physical host with other active mesh agents | Best immediate free implementation slot if shared-host governor allows |
| `highload` | `offline-route` | highload mesh/server metadata | no live resource stats; mesh card `mesh-highload` degraded | no live Agent Host; degraded mesh shadow only | not verified; stale metadata advertises generic implementation | fallback relay only; no runner evidence on live card | mesh degraded/stale >15h; metadata stale >38h | 0 | no live Agent Host/resource stats | Reinstall or restart Agent Host heartbeat; verify resources and runner capabilities before scheduling |
| `paris` | `offline-route` | remote implementation metadata | no live resource stats; mesh card `mesh-paris` degraded | no live Agent Host; degraded mesh shadow only | not verified; stale metadata advertises generic implementation | fallback relay only; no runner evidence on live card | mesh degraded/stale >15h; metadata stale >38h | 0 | no live Agent Host/resource stats | Restore Agent Host and retire stale metadata if server is no longer in fleet |
| `reserve242` | `offline-route` | reserve implementation metadata | no live resource stats; mesh card `mesh-reserve242` degraded | no live Agent Host; degraded mesh shadow only | not verified; stale metadata advertises generic implementation | fallback relay only; no runner evidence on live card | mesh degraded/stale >15h; metadata stale >38h | 0 | no live Agent Host/resource stats | Restore reserve Agent Host heartbeat or mark as standby/offline explicitly |
| `server-kfrm` | `offline-route` | remote implementation metadata | no live resource stats; mesh card `mesh-server-kfrm` degraded | no live Agent Host; degraded mesh shadow only | not verified; stale metadata advertises generic implementation | fallback relay only; no runner evidence on live card | mesh degraded/stale >15h; metadata stale >38h | 0 | no live Agent Host/resource stats | Restore Agent Host heartbeat and validate GitHub/Codex/MIMO before target-pool inclusion |

## Rollup

| Class | Count | Servers |
| --- | ---: | --- |
| `ready` | 10 | `new`, `agent-01`, `agent-02`, `agent-03`, `agent-04`, `agent-05`, `agent-06`, `agent-07`, `agent-08`, `agent-09` |
| `partial` | 5 | `home`, `main`, `uiap`, `qjns`, `9fts` |
| `repair` | 1 | `primary` |
| `offline-route` | 4 | `highload`, `paris`, `reserve242`, `server-kfrm` |

Immediate safe routing pool:

- Implementation: `agent-08`, `agent-09`, then `agent-01..07` only if active task and shared-host capacity permit.
- Review/QA: `new`; `main` only for bounded probes because RAM is low.
- RAG: `uiap` only for knowledge/RAG work.
- Owner gateway/Telegram: no broad dispatch until `home`/`home-live` identity and freshness are stable.

Required repair queue:

1. Normalize `primary` identity and restore heartbeat freshness.
2. Run qjns GitHub/Codex/MIMO credential smoke on node-local Agent Host.
3. Retire or refresh stale metadata cards for `9fts`, `agent-01..09`, `highload`, `paris`, `reserve242`, and `server-kfrm`.
4. Restore live Agent Host routes for `highload`, `paris`, `reserve242`, and `server-kfrm`, or mark them explicitly offline.
5. Enforce shared-host 50 percent capacity across `agent-01..09` because they report the same physical host/resources.
