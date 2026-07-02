# Next Tasks And Blockers

## Exact Next Tasks

1. Dispatch `P0_GOMESH_SPEED_GATE_CANARY_FAST_EXIT_PROBE_2026_07_01` or a dated successor to a healthy GoMesh-capable server node.
2. In that task, run a supervised canary only; do not promote whole-LAN routing.
3. Measure direct path and GoMesh tunnel throughput for each candidate exit using the same target and comparable test method.
4. Require a passing production gate before selector promotion: direct capacity and tunnel result must support `300+ Mbps` with bounded latency and no DNS/TCP/UDP regression.
5. Record rollback commands before any selector change.
6. If no current exit can pass, open a separate optimization task for dataplane tuning, exit capacity, MTU, QUIC/TCP fallback, and egress bottleneck isolation.
7. After one exit passes, dispatch a narrow canary promotion task for one source IP or test host only.

## Current Blockers

- No fresh repository evidence proves a `300+ Mbps` GoMesh path.
- Last known numbers are below target: direct `159 Mbps`, GoMesh `66.7 Mbps`, target `300+ Mbps`.
- Selector must remain in safe mode because eligible exits are `0` in the latest recorded speed-gate evidence.
- Whole-LAN rollout remains blocked until one-host canary metrics are stable.
- The previous read-only GoMesh supervision result noted a runner permission caveat: a read-only envelope still received broad permissions. Keep future speed-gate tasks explicitly read-only until mutation is required and approved.

## Required Evidence For Unblocking

- Speed-gate report with direct Mbps, GoMesh Mbps, target, exit endpoint, test host, transport mode, MTU, DNS result, TCP result, UDP/QUIC result, and selector decision.
- Confirmation that no secrets were printed.
- Confirmation that rollback was prepared before any promotion.
- Confirmation that product code remained unchanged unless a separate implementation task explicitly allowed it.

