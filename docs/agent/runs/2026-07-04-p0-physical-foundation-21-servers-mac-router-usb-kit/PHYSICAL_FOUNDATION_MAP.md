# PHYSICAL_FOUNDATION_MAP.md

**Date:** 2026-07-04T22:20:00Z

## Infrastructure Classes

### 1. Physical Servers (21 canonical)
Home, main, primary-candidate, uiap, qjns, 9fts, new, server-kfrm, reserve242, highload, paris, agent-01 through agent-10.

### 2. Command Nodes
- **Mac** (owner command client) — not an execution server
- **Home** (physical NOC + control plane host)
- **primary-candidate** (server-side control authority)
- **main** (fallback control/execution)

### 3. Network Nodes
- **MikroTik router** (178.207.11.90) — home edge, VPN gateway
- **WireGuard mesh** — 10.99.0.0/24 VPN network
- **Kolibri Mesh** — custom mesh VPN on port 8080

### 4. Operator Assets
- **USB operator kit** — emergency recovery package
- **SSH key** (Kolibri SSH Key) — unified deploy key
- **Recovery docs** — offline bootstrap runbook

### 5. Logical Workers
- mesh-agent-01 through mesh-agent-101 (on kolibri node)
- Agent Host records in Control Plane
- MIMO/Codex/API agent records

## Physical → Logical Mapping

| Physical Server | Logical Workers | Control Plane Record |
|-----------------|-----------------|---------------------|
| home | home, home-live, coordinator | fresh |
| main | main | fresh |
| primary-candidate | primary-candidate, primary | fresh |
| uiap | uiap | fresh |
| qjns | qjns | fresh |
| 9fts | 9fts | fresh |
| new | new | fresh |
| server-kfrm | server-kfrm | fresh |
| reserve242 | — | fresh |
| highload | — | fresh |
| paris | — | fresh |
| agent-01..10 | agent-01..10 | fresh (except agent-10) |
| kolibri (primary) | mesh-agent-01..101 | fresh |

## Critical Dependencies

1. Home must be online for Control Plane
2. Router must be online for VPN connectivity
3. Mac is NOT required for factory runtime
4. GitHub is required for code sync but not for execution
