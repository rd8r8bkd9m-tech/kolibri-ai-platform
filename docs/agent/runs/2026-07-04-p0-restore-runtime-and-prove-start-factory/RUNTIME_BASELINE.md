# RUNTIME_BASELINE.md

**Date:** 2026-07-04T21:52:00Z
**Phase:** 1 — Runtime Baseline (read-only)

## Control Plane Authority

| Endpoint | Health | Redis | Status |
|----------|--------|-------|--------|
| `http://10.99.0.1:9101` (home) | ok | PONG | **AUTHORITATIVE** |
| `http://10.99.0.2:9101` (main) | UNREACHABLE | — | dead |
| `http://10.99.0.10:9101` (primary) | UNREACHABLE | — | dead |

**Authoritative Control Plane:** `http://10.99.0.1:9101` (home)
**Queue backend:** Redis on 127.0.0.1:6379

## Node Inventory

**Total nodes indexed:** 117

| Health | Count |
|--------|-------|
| online | 5 |
| fresh | 5 |
| degraded | 65 |
| stale | 47 |

### Real server nodes (non-mesh)

| Node ID | Hostname | Health | Heartbeat Age | Runners |
|---------|----------|--------|---------------|---------|
| home | plastilin | stale | — | — |
| home-live | plastilin | degraded | — | — |
| main | kolibri-main-api | degraded | — | — |
| primary-candidate | kolibri | degraded | — | — |
| server-kfrm | server-kfrm | degraded | — | — |
| 9fts-loop-test | MacBook-Air-Vladislav.local | stale | 6658s | codex,mimo |
| demo-node | x | stale | 9899s | — |
| demo-node2 | MacBook-Air-Vladislav.local | stale | 9890s | codex,mimo |
| remote-loop01 | MacBook-Air-Vladislav.local | stale | 6674s | — |
| watcher-inline | mac | stale | — | — |

### Mesh agents: 101 registered on kolibri node

- ~42 online, ~15 degraded, ~44 stale
- All target `kolibri` as hostname
- Capabilities: mesh, mesh_node, implementation, generic_implementation

## Mesh Coordinator (port 8080)

| Node | IP | Status |
|------|----|--------|
| home | 10.99.0.1 | online |
| main | 10.99.0.2 | online |
| primary | 10.99.0.10 | online |
| qjns | 10.99.0.4 | online |
| 9fts | 10.99.0.5 | **offline** |
| uiap | 10.99.0.3 | **offline** |
| new | 10.99.0.6 | **offline** |

**Offline due to broken VPN tunnels** (100% packet loss 9fts/uiap/new → 10.99.0.1)

## Task Inventory

| Metric | Value |
|--------|-------|
| Total indexed | 298 |
| Queue length | 0 |
| Running | 12 |
| Leased | 1 |
| Queued | 10 (8 visible) |
| Completed | 77 |
| Failed | 129 (100 sampled) |
| Dead letter | 63 |
| Cancelled | 1 |

## Running Index Drift

**running_index = 12, active_summary = 0**

This is a critical drift. 12 tasks are marked "running" in the state index, but the active summary returns 0 active tasks. Root cause: tasks completed/failed but the running index was not decremented.

## Failed Task Breakdown (100 sampled)

| Error Type | Count |
|------------|-------|
| runner_execution_failed | 85 |
| runtime_error | 11 |
| runner_unavailable | 4 |

| Runner | Failures |
|--------|----------|
| mimo | 92 |
| codex | 6 |
| None | 2 |

Top target nodes: mesh-agent-* (distributed failures), home, home-thin-watcher

## Dead Letter Breakdown

All 63 dead_letter tasks have `error_type=lease_expired`. These are tasks that exceeded lease duration without completion.

## Agent Host Heartbeat Analysis

- **Fresh online nodes:** ~5 (home, main, qjns, primary, server-kfrm via mesh)
- **Degraded:** 65 — these are physical servers or mesh agents with stale heartbeats
- **Stale:** 47 — no heartbeat received recently

**Root cause of degradation:** Most agent-host processes connect to Control Plane at 10.99.0.2:9101 (main) which is **unreachable**. Only agents connecting to 10.99.0.1:9101 (home) are fresh.

## SSH Connectivity (from MacBook)

All 21 servers accessible via SSH config aliases through home-wg (VPN) or primary-codex (ProxyJump).

## Key Findings

1. **Single point of failure:** Only home Control Plane is alive. Main and primary CPs are dead.
2. **Mass agent misconfiguration:** Most agent-host processes point to 10.99.0.2:9101 which is unreachable.
3. **Running index drift:** 12 running tasks with 0 active — phantom running state.
4. **85% runner_execution_failed:** MIMO runner failures dominate — likely timeout or auth issues.
5. **63 lease_expired dead letters:** Tasks stuck without heartbeat refresh.
6. **3 mesh nodes offline:** VPN tunnel failures to 9fts/uiap/new.
