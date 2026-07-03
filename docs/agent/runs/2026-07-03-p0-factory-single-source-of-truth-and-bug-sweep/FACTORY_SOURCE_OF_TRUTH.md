# Factory Source Of Truth

Primary static source: `ops/factory_registry.py`.

Primary runtime source: Control Plane Fabric API:

- `GET /v1/nodes`
- `GET /v1/fleet/nodes`
- `GET /v1/fleet/summary`
- `GET /v1/fleet/registry`
- `GET /v1/fleet/drift`
- `GET /v1/fleet/capabilities`
- `GET /v1/fleet/route`
- `GET /v1/tasks/queue/diagnostics`

Agents must read registry and Fabric API before answering technical questions about servers, ports, queue state, runners or fallbacks.

## Snapshot

- CP records total: 135.
- Fresh records: 32.
- Stale records: 103.
- Online records: 28.
- Degraded records: 4.
- Logical mesh-agent records in CP: 101.
- Active logical worker units observed: 20.
- Queue records observed in live summary: 18.
- Blocked tasks observed in live summary: 9.

These numbers are evidence from 2026-07-03 live probes and must be refreshed after deployment.

