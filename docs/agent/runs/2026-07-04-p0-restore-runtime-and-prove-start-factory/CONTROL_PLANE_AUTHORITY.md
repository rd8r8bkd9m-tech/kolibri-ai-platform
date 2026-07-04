# CONTROL_PLANE_AUTHORITY.md

**Date:** 2026-07-04T21:55:00Z
**Phase:** 2 — Control Plane Authority

## Findings

### Endpoint Health

| CP | URL | Health | Nodes | Tasks | Can Submit | Split Brain |
|----|-----|--------|-------|-------|------------|-------------|
| home | http://10.99.0.1:9101 | ok | 117 | 298 | YES | — |
| main | http://10.99.0.2:9101 | DEAD | — | — | NO | — |
| primary | http://10.99.0.10:9101 | DEAD | — | — | NO | — |

### Decision

- **authoritative_control_plane:** `http://10.99.0.1:9101`
- **worker_control_plane:** `http://10.99.0.1:9101` (all workers must use this)
- **gateway_control_plane:** `http://10.99.0.1:9101`
- **home_noc_control_plane:** `http://10.99.0.1:9101`
- **split_brain:** NO (main and primary are dead, not diverged)

### Root Cause of CP Death

Main (10.99.0.2) and primary (10.99.0.10) Control Planes are unreachable from home VPN. This may be:
1. Process crashed and not restarted
2. Network issue between home and these nodes
3. Firewall blocking port 9101

### Required Fix

All agent-host processes across the fleet must be reconfigured to use `http://10.99.0.1:9101` as their control URL. Currently many point to `http://10.99.0.2:9101` (main) which is dead.
