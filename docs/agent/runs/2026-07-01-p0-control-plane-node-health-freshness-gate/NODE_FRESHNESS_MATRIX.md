# Node Freshness Matrix

Evidence before the patch:

| Metric | Value |
| --- | ---: |
| Control Plane node cards | 42 |
| Cards reporting `health=online` | 32 |
| Heartbeats fresh <=5m | 9 |
| Heartbeats fresh <=30m | 9 |
| Heartbeats stale >30m | 33 |

Examples of stale cards previously reported as online:

| Node | Reported health | Heartbeat age |
| --- | --- | ---: |
| `home` | `online` | ~503 minutes |
| `mesh-qjns` | `online` | ~535 minutes |
| `agent-01` | `online` | ~1880 minutes |

Proposed contract in PR #97:

| Freshness | Rule | Online count behavior |
| --- | --- | --- |
| `fresh` | heartbeat age <=30s | may count online if health is online |
| `degraded` | heartbeat age >30s | not fully online |
| `stale` | heartbeat age >90s or missing heartbeat | not online |

The exact thresholds are configurable with `FACTORY_NODE_DEGRADED_AFTER` and `FACTORY_NODE_STALE_AFTER`.
