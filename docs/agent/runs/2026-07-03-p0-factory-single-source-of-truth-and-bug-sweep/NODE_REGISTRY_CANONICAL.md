# Canonical Node Registry

Canonical registry lives in `ops/factory_registry.py`.

## Physical / Canonical Servers

| Canonical ID | Type | Internal IPs | External IPs | Notes |
| --- | --- | --- | --- | --- |
| home | hybrid_node | 10.99.0.1 | 178.207.11.90 | Gateway and command path |
| main | hybrid_node | 10.99.0.2 | 104.253.43.117 | Control plane path |
| primary-candidate | hybrid_node | 10.99.0.10 | 78.17.4.108 | Current primary candidate, frontend/backend/control services |
| uiap | execution_node | 10.99.0.3 | 31.57.26.151 | Knowledge node |
| qjns | execution_node | 10.99.0.4 | 217.60.63.97 | Test/review tooling node |
| 9fts | execution_node | 10.99.0.5 | 94.183.235.154 | Implementation/model node |
| new | execution_node | 10.99.0.6 | 109.248.161.39 | Review/backup worker |
| server-kfrm | physical_server | | 217.60.63.31 | Reserve |
| reserve242 | physical_server | | 31.57.26.242 | Reserve |
| highload | physical_server | | 45.38.139.182 | Reserve |
| paris | physical_server | | 95.182.83.60 | Reserve |
| agent-01..agent-10 | physical_server | | see registry | Reserve agent servers |

## Counts

- Canonical physical records in registry: 21.
- Runtime CP records observed: 135.
- Runtime canonical physical servers represented in Control Plane: 20.
- Runtime missing canonical server: agent-10.
- Runtime stale records observed: 103.
- Runtime logical workers observed in CP: 101.

Do not invent mappings for records outside the registry. Unknown records must be reported by `/v1/fleet/drift`.
