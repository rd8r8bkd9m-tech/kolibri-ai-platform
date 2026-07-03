# Technical Answer Policy

Agents must not answer from memory when registry or Fabric API can answer.

## Required Source Order

1. `ops/factory_registry.py` for canonical identity and ports.
2. `/v1/fleet/summary` for current counts.
3. `/v1/fleet/nodes` for detailed node state.
4. `/v1/tasks/queue/diagnostics` for leaseable or blocked tasks.
5. `/v1/fleet/drift` for unknown, stale or duplicate records.

## Prohibited Answers

- "server unavailable" without evidence and fallback.
- "unknown" without a diagnostic source.
- completed status without artifacts or explicit partial status.
- guessed ports.
- guessed runner status.

