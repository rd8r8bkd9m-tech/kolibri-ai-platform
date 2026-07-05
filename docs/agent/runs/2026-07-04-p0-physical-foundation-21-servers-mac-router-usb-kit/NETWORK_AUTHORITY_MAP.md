# NETWORK_AUTHORITY_MAP.md

**Date:** 2026-07-04T22:20:00Z

| Asset | Class | Authority Layer | Can Execute Tasks | Can Dispatch Tasks | Criticality |
|-------|-------|-----------------|-------------------|-------------------|-------------|
| Mac | command_node | owner command | no | yes | medium |
| Home | physical_server | NOC + control plane | yes | yes | critical |
| MikroTik | network_node | edge router/VPN | no | no | critical |
| primary-candidate | physical_server | control authority | yes | yes | high |
| main | physical_server | fallback control | yes | yes | high |
| server-kfrm | physical_server | execution | yes | no | high |
| GitHub | external | code source-of-truth | no | no | high |
| Control Plane | service | task/agent state | no | no | critical |
| Redis | service | queue/cache | no | no | high |
| USB kit | operator_kit | emergency recovery | no | no | medium |

## Rules
- Mac is NOT required for factory runtime
- Router is NOT an execution node
- USB kit is NOT a network or worker node
- Redis is NOT the sole source of truth
