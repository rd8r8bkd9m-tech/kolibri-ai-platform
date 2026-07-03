# Network Reachability Matrix

Snapshot: 2026-07-03T13:47Z.

Scope: canonical physical/hybrid/execution servers from `CANONICAL_NODE_REGISTRY`, not logical worker records.

## Summary

- Canonical servers in registry: 21.
- Canonical servers currently represented in Control Plane: 20.
- Missing from Control Plane: `agent-10`.
- Fresh/online or service-proven servers: `9fts`, `home`, `main`, `primary-candidate`, `server-kfrm`.
- Fresh but degraded/not schedulable servers: `new`, `qjns`, `uiap`.
- Stale but network-reachable reserve/agent servers: `agent-01` through `agent-09`, `highload`, `paris`, `reserve242`.
- Offline or network-blocked: `agent-10`.
- `agent-10` is now quarantined in registry diagnostics as `provider_network_unreachable`.
- Public-key SSH from the command node is blocked on every checked root target except Home via the repaired `ladik` key path.

ICMP is not authoritative. `primary-candidate` rejects ping but serves TCP/HTTP on the expected service ports.

## Canonical Server Matrix

| Node | Internal IP | External IP | CP status | Network evidence | SSH key auth | Final status | Repair action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| home | 10.99.0.1 | 178.207.11.90 | fresh online | internal/external ping ok, SSH TCP ok | ok as `ladik` | online | keep Home key path and kiosk rollback |
| main | 10.99.0.2 | 104.253.43.117 | fresh online | internal/external ping ok, `10.99.0.2:9101` TCP ok | blocked for root | online, SSH trust blocked | repair root/deploy key trust or use Fabric API only |
| primary-candidate | 10.99.0.10 | 78.17.4.108 | fresh online | service ports 5173/9101/19131/19132 ok internally; 5173/19131/19132 ok externally; ICMP blocked | blocked for root | online, SSH trust blocked | keep API as primary path; repair deploy key trust separately |
| uiap | 10.99.0.3 | 31.57.26.151 | fresh degraded | internal/external ping ok, SSH TCP ok | blocked for root | degraded | repair node health/agent host and root/deploy key trust |
| qjns | 10.99.0.4 | 217.60.63.97 | fresh degraded | internal/external ping ok, SSH TCP ok | blocked for root | degraded | repair node health/agent host and root/deploy key trust |
| 9fts | 10.99.0.5 | 94.183.235.154 | fresh online | internal/external ping ok, SSH TCP ok | blocked for root | online, SSH trust blocked | repair root/deploy key trust; do not fake Codex runner |
| new | 10.99.0.6 | 109.248.161.39 | fresh degraded | SSH TCP ok; ICMP blocked | blocked for root | degraded | repair node health/agent host and root/deploy key trust |
| server-kfrm | | 217.60.63.31 | fresh online | external ping ok, SSH TCP ok | blocked for root | online, SSH trust blocked | repair root/deploy key trust |
| reserve242 | | 31.57.26.242 | stale | external ping ok, SSH TCP ok | blocked for root | stale reachable | classify reserve state; bootstrap agent or retire |
| highload | | 45.38.139.182 | stale | SSH TCP ok; ICMP blocked | blocked for root | stale reachable | classify reserve state; bootstrap agent or retire |
| paris | | 95.182.83.60 | stale | external ping ok, SSH TCP ok | blocked for root | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-01 | | 31.57.27.128 | stale | external ping ok, SSH TCP ok | blocked for root | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-02 | | 213.232.204.223 | stale | external ping ok, SSH TCP ok | blocked for root | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-03 | | 188.130.206.204 | stale | external ping ok, SSH TCP ok | blocked for root | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-04 | | 31.59.41.146 | stale | external ping ok, SSH TCP ok | blocked for root | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-05 | | 31.56.196.10 | stale | external ping ok, SSH TCP ok | blocked for root | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-06 | | 45.39.33.252 | stale | external ping ok, SSH TCP ok | blocked for root | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-07 | | 46.8.225.34 | stale | external ping ok, SSH TCP ok | blocked for root | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-08 | | 31.59.105.200 | stale | external ping ok, SSH TCP ok | blocked for root | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-09 | | 95.182.84.254 | stale | external ping ok, SSH TCP ok | blocked for root | stale reachable | classify reserve state; bootstrap agent or retire |
| agent-10 | | 217.60.38.191 | registry-only, missing heartbeat | no ping, no SSH TCP, upstream `46.8.226.1` returns host unreachable | blocked/unreachable | quarantined: provider_network_unreachable | provider/network repair or retire from registry after owner approval |

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

Additional checks from `primary-candidate` and Home both route toward `217.60.38.191` and fail at upstream `46.8.226.1` with Destination Host Unreachable / `!H`.

No alternate `agent-10` IP was found in repo inventory, SSH topology or docs.

Runtime diagnostics fix:

- Registry keeps `agent-10` visible as a canonical server.
- `/v1/fleet/drift` now reports `agent-10` in `registry_nodes_missing_in_control_plane`.
- `/v1/fleet/drift` now reports `agent-10` in `registry_only_records`.
- `/v1/fleet/registry` marks `agent-10` as `lifecycle=quarantined`, `network_status_override=provider_network_unreachable`, `safe_to_schedule=false`.

Rollback backups:

- `/var/backups/kolibri-agent10-drift-fix-20260703T140705Z`
- `/var/backups/kolibri-agent10-quarantine-20260703T140745Z`

Rollback backup for the registry deploy:

- `/var/backups/kolibri-p0-network-foundation-20260703T134617Z/factory_registry.py`

## Repair Tasks

1. `P0_REPAIR_FACTORY_SSH_TRUST_BOOTSTRAP_20260703`: restore command-node deploy public-key trust or replace it with an audited Fabric bootstrap path across root-managed servers. Do not print secrets. Back up `authorized_keys` before edits.
2. `P0_REPAIR_AGENT10_NETWORK_OR_RETIRE_20260703`: verify provider console/network route for `217.60.38.191`; either restore SSH/network reachability or retire/quarantine the canonical record with owner approval.
3. `P0_REPAIR_DEGRADED_EXECUTION_NODES_20260703`: repair `uiap`, `qjns`, and `new` health/agent-host state before scheduling heavy work.
4. `P0_CLASSIFY_STALE_RESERVE_SERVERS_20260703`: classify `agent-01..agent-09`, `highload`, `paris`, and `reserve242` as retired, planned, quarantined or broken.

## Policy

- Do not classify ICMP failure alone as offline.
- Do not mark a server scheduleable unless Control Plane heartbeat is fresh and node health is online/non-degraded.
- Do not claim SSH management works when public-key auth fails.
- Do not delete stale records during this sweep.

## SSH Identity Standardization Update

Snapshot: 2026-07-03T16:12Z.

Canonical `ssh_access` metadata is now exposed by `/v1/fleet/registry` for every server:

- `home`: `direct_internal`, target `10.99.0.1`, user `ladik`, identity `kolibri_home_repair_20260703_ed25519`.
- `main`: `internal_via_home`, target `10.99.0.2`, user `root`, identity `kolibri_ai_platform_deploy_ed25519`.
- `qjns`: `internal_via_home`, target `10.99.0.4`, user `root`, identity `kolibri_ai_platform_deploy_ed25519`.
- `uiap`, `9fts`, `new`, `primary-candidate`: `internal_via_main`, target is the registry internal IP, user `root`.
- reserve/agent external-only servers: `external_via_main`, target is the registry external IP, user `root`.

Bootstrap access confirmed:

| Alias | Result |
| --- | --- |
| `ssh kolibri-home` | ok, `plastilin`, `ladik`, agent active |
| `ssh kolibri-main` | ok, `kolibri-main-api`, `root`, agent active |
| `ssh kolibri-qjns` | ok, `kolibri-tools-executor`, `root`, agent active |

Current key gap:

- The remaining target servers are reachable through the standardized jump path where TCP allows it, but root deploy-key auth is not yet installed on the target hosts.
- Next repair action is per-host authorized-key bootstrap with backup, not route guessing.

Rollback backup for live registry metadata deploy:

- `/var/backups/kolibri-ssh-access-registry-20260703T161203Z`
