# Node Alias Registry

Alias source: `NODE_ALIAS_MAP` and `canonical_node_id()` in `ops/factory_registry.py`.

| Alias | Canonical |
| --- | --- |
| home-live | home |
| mesh-home | home |
| primary | primary-candidate |
| mesh-primary | primary-candidate |
| direct | primary-candidate |
| rag | uiap |
| mesh-uiap | uiap |
| tools | qjns |
| mesh-qjns | qjns |
| inference | 9fts |
| mesh-9fts | 9fts |
| worker-backup | new |
| mesh-new | new |
| mesh-main | main |

## Safety Rule

`mesh-agent-*` records are logical workers and are not aliases for physical `agent-*` reserve servers.

