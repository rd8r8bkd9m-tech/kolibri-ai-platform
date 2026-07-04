# Network Reachability Matrix

Snapshot: 2026-07-04T07:06Z.

Scope: canonical physical/hybrid/execution servers from `CANONICAL_NODE_REGISTRY`, not logical worker records.

## Summary

- Canonical servers in registry: 21.
- Canonical servers currently represented in Control Plane: 21.
- Missing from Control Plane: none.
- Fresh/online or service-proven servers: `9fts`, `agent-10`, `home`, `main`, `primary-candidate`, `server-kfrm`.
- Fresh but degraded/not schedulable servers: `new`, `qjns`, `uiap`.
- Stale but network-reachable reserve/agent servers: `agent-01` through `agent-09`, `highload`, `paris`, `reserve242`.
- Offline or network-blocked: none among canonical physical servers.
- `agent-10` is now reachable through WireGuard as `10.99.0.18`; external public IP `217.60.38.191` is still not a reliable direct management path from every source.
- Public-key SSH from the command node works on 21 of 21 canonical servers through the unified alias topology.

ICMP is not authoritative. `primary-candidate` rejects ping but serves TCP/HTTP on the expected service ports.

## Canonical Server Matrix

| Node | Internal IP | External IP | CP status | Network evidence | SSH key auth | Final status | Repair action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| home | 10.99.0.1 | 178.207.11.90 | fresh online | internal/external ping ok, SSH TCP ok | ok as `ladik` | online | keep Home key path and kiosk rollback |
| main | 10.99.0.2 | 104.253.43.117 | fresh online | internal/external ping ok, `10.99.0.2:9101` TCP ok | ok as `root` via `kolibri-main` | online | keep unified key path |
| primary-candidate | 10.99.0.10 | 78.17.4.108 | fresh online | service ports 5173/9101/19131/19132 ok internally; 5173/19131/19132 ok externally; ICMP blocked | ok as `root` via `kolibri-primary-candidate` | online | keep API as primary path |
| uiap | 10.99.0.3 | 31.57.26.151 | fresh degraded | internal/external ping ok, SSH TCP ok | ok as `root` via `kolibri-uiap` | degraded | repair node health/agent host |
| qjns | 10.99.0.4 | 217.60.63.97 | fresh degraded | internal/external ping ok, SSH TCP ok | ok as `root` via `kolibri-qjns` | degraded | repair node health/agent host |
| 9fts | 10.99.0.5 | 94.183.235.154 | fresh online | internal/external ping ok, SSH TCP ok | ok as `root` via `kolibri-9fts` | online | do not fake Codex runner |
| new | 10.99.0.6 | 109.248.161.39 | fresh degraded | SSH TCP ok; ICMP blocked | ok as `root` via `kolibri-new` | degraded | repair node health/agent host |
| server-kfrm | | 217.60.63.31 | fresh online | external ping ok, SSH TCP ok | ok as `root` via `server-kfrm` | online | keep unified key path |
| reserve242 | | 31.57.26.242 | stale | external ping ok, SSH TCP ok | ok as `root` via `reserve242` | stale reachable | classify reserve state; bootstrap agent or retire |
| highload | | 45.38.139.182 | stale | SSH TCP ok; ICMP blocked | ok as `root` via `highload` | stale reachable | classify reserve state; bootstrap agent or retire |
| paris | | 95.182.83.60 | stale | external ping ok, SSH TCP ok | ok as `root` via `paris` | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-01 | | 31.57.27.128 | stale | external ping ok, SSH TCP ok | ok as `root` via `agent-01` | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-02 | | 213.232.204.223 | stale | external ping ok, SSH TCP ok | ok as `root` via `agent-02` | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-03 | | 188.130.206.204 | stale | external ping ok, SSH TCP ok | ok as `root` via `agent-03` | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-04 | | 31.59.41.146 | stale | external ping ok, SSH TCP ok | ok as `root` via `agent-04` | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-05 | | 31.56.196.10 | stale | external ping ok, SSH TCP ok | ok as `root` via `agent-05` | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-06 | | 45.39.33.252 | stale | external ping ok, SSH TCP ok | ok as `root` via `agent-06` | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-07 | | 46.8.225.34 | stale | external ping ok, SSH TCP ok | ok as `root` via `agent-07` | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-08 | | 31.59.105.200 | stale | external ping ok, SSH TCP ok | ok as `root` via `agent-08` | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-09 | | 95.182.84.254 | stale | external ping ok, SSH TCP ok | ok as `root` via `agent-09` | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-10 | 10.99.0.18 | 217.60.38.191 | fresh online | WireGuard route ok, agent host active; direct external TCP is source-dependent | ok as `root` via `agent-10` | online | keep internal mesh route as canonical management path |

## Service Ports Verified

| Service | URL | Result |
| --- | --- | --- |
| Control Plane | http://10.99.0.10:9101/v1/health | 200 |
| Backend staging | http://10.99.0.10:19131/api/health | 200 |
| Frontend preview | http://10.99.0.10:19132/ | 200 |
| Frontend dev | http://10.99.0.10:5173/ | 200 |
| Backend staging external | http://78.17.4.108:19131/api/health | 200 |
| Frontend preview external | http://78.17.4.108:19132/ | 200 |
| Frontend dev external | http://78.17.4.108:5173/ | 200 |
| Main control internal | http://10.99.0.2:9101/v1/health | 200 |

## Source-Of-Truth API Fix

Bug found during this sweep: `/v1/fleet/registry` exposed only fallback/service nodes and omitted reserve/agent physical servers.

Fix: `fabric_node_catalog()` now returns the full `CANONICAL_NODE_REGISTRY`.

Live verification after deploy:

- `/v1/fleet/registry` node count: 21.
- `agent-10` present: yes.
- `reserve242` present: yes.
- `/v1/registry/validate`: completed with no errors.

## Agent-10 Incident Update

Updated 2026-07-04: physical `agent-10` is online again through the mesh route.

- Hostname: `kolibri-hk-edge-load`.
- Internal IP: `10.99.0.18`.
- External IP: `217.60.38.191`.
- Agent Host: active.
- SSH: `ssh agent-10` works as `root` with `kolibri_ai_platform_deploy_ed25519`.
- Canonical management path: `10.99.0.18` via `kolibri-main`.
- External direct TCP remains source-dependent and must not be the primary management path.

`mesh-agent-10` remains a separate logical worker on hostname `kolibri`. It is not an alias for physical `agent-10`.

Runtime diagnostics fix:

- Registry keeps `agent-10` visible as a canonical physical server.
- `/v1/nodes` reports `agent-10` as fresh/online.
- `/v1/fleet/registry` records `agent-10` internal IP `10.99.0.18`, external IP `217.60.38.191`, lifecycle `active`.

Rollback backups:

- `/var/backups/kolibri-agent10-drift-fix-20260703T140705Z`
- `/var/backups/kolibri-agent10-quarantine-20260703T140745Z`

Rollback backup for the registry deploy:

- `/var/backups/kolibri-p0-network-foundation-20260703T134617Z/factory_registry.py`

## Repair Tasks

1. `P0_REPAIR_FACTORY_SSH_TRUST_BOOTSTRAP_20260703`: completed for reachable servers; keep backups and audit trail. Future key changes must use the same backed-up, per-host bootstrap path.
2. `P0_REPAIR_AGENT10_NETWORK_OR_RETIRE_20260703`: completed by restoring the mesh management route; keep direct external reachability as a lower-priority provider check.
3. `P0_REPAIR_DEGRADED_EXECUTION_NODES_20260703`: repair `uiap`, `qjns`, and `new` health/agent-host state before scheduling heavy work.
4. `P0_CLASSIFY_STALE_RESERVE_SERVERS_20260703`: classify `agent-01..agent-09`, `highload`, `paris`, and `reserve242` as retired, planned, quarantined or broken.

## Policy

- Do not classify ICMP failure alone as offline.
- Do not mark a server scheduleable unless Control Plane heartbeat is fresh and node health is online/non-degraded.
- Do not claim SSH management works unless alias-based public-key auth has been verified from the command node.
- Do not delete stale records during this sweep.

## SSH Identity Standardization Update

Snapshot: 2026-07-03T16:12Z.

Canonical `ssh_access` metadata is now exposed by `/v1/fleet/registry` for every server:

- `home`: `direct_internal`, target `10.99.0.1`, user `ladik`, identity `kolibri_ai_platform_deploy_ed25519`.
- `main`: `internal_via_home`, target `10.99.0.2`, user `root`, identity `kolibri_ai_platform_deploy_ed25519`.
- `qjns`: `internal_via_home`, target `10.99.0.4`, user `root`, identity `kolibri_ai_platform_deploy_ed25519`.
- `uiap`, `9fts`, `new`, `primary-candidate`, `agent-10`: `internal_via_main`, target is the registry internal IP, user `root`.
- reserve/agent external-only servers except `agent-10`: `external_via_main`, target is the registry external IP, user `root`.

Bootstrap access confirmed:

| Alias | Result |
| --- | --- |
| `ssh kolibri-home` | ok, `plastilin`, `ladik`, agent active |
| `ssh kolibri-main` | ok, `kolibri-main-api`, `root`, agent active |
| `ssh kolibri-qjns` | ok, `kolibri-tools-executor`, `root`, agent active |
| `ssh kolibri-primary-candidate` | ok, `kolibri`, `root`, agent active |
| `ssh kolibri-uiap` | ok, `kolibri-rag-knowledge`, `root`, agent active |
| `ssh kolibri-9fts` | ok, `kolibri-inference-recovery`, `root`, agent active |
| `ssh kolibri-new` | ok, `kolibri-worker-backup`, `root`, agent active |
| `ssh reserve242` | ok, `kolibri-qa-security`, `root`, agent active |
| `ssh highload` | ok, `kolibri-ci-build-highload`, `root`, agent active |
| `ssh agent-01` | ok, `kolibri-backend-lead`, `root`, agent active |
| `ssh agent-02` | ok, `kolibri-frontend-design`, `root`, agent active |
| `ssh agent-03` | ok, `kolibri-infra-network`, `root`, agent reachable |
| `ssh agent-04` | ok, `kolibri-qa-browser`, `root`, agent active |
| `ssh agent-05` | ok, `kolibri-security-audit`, `root`, agent active |
| `ssh agent-06` | ok, `kolibri-docs-knowledge`, `root`, agent active |
| `ssh agent-07` | ok, `kolibri-formulalm-eval`, `root`, agent active |
| `ssh agent-08` | ok, `kolibri-rag-eval`, `root`, agent active |
| `ssh agent-09` | ok, `kolibri-release-canary`, `root`, agent active |
| `ssh paris` | ok, `kolibri-paris-build-reserve`, `root`, agent active |
| `ssh server-kfrm` | ok, `server-kfrm`, `root`, agent active |
| `ssh agent-10` | ok, `kolibri-hk-edge-load`, `root`, agent active |

Current key gap:

- No remaining SSH key-auth gap was found on canonical servers.
- `agent-10` management must use the internal mesh target `10.99.0.18`; direct external `217.60.38.191` is not reliable from every source.

Rollback backup for live registry metadata deploy:

- `/var/backups/kolibri-ssh-access-registry-20260703T161203Z`
