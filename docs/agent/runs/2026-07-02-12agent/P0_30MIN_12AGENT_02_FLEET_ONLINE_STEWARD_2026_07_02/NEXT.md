# NEXT

Exact next tasks:

1. `P0_FLEET_CANONICAL_20_SERVER_IDENTITY_REPAIR_2026_07_02`
   - Goal: produce the exact canonical 20-server list, map every Control Plane card and mesh shadow to one canonical identity, and identify the two missing canonical identities.
   - Target nodes: `main`, `new`, or `uiap`.
   - Guardrails: read-only, no product code, no secrets, no credential mutation.

2. `P0_FLEET_STALE_CARD_RETENTION_AND_DEDUP_REPAIR_2026_07_02`
   - Goal: add or run a safe Control Plane maintenance path that marks stale duplicate cards as metadata debt and prevents them from being counted as capacity.
   - Target nodes: `main` or `primary-candidate` after freshness is restored.
   - Guardrails: no destructive delete until owner-approved; first pass should be report-only.

3. `P0_HOME_AND_PRIMARY_HEARTBEAT_FRESHNESS_REPAIR_2026_07_02`
   - Goal: restore fresh heartbeats for `home`, `home-live`, and `primary-candidate`, then reclassify them as full, partial, degraded, or stale.
   - Target nodes: `main`, `new`, or a fresh mesh agent.
   - Guardrails: no service restart unless the task explicitly includes rollback and owner approval.

4. `P0_FLEET_QUEUE_RETENTION_AND_PRIORITY_DRAIN_2026_07_02`
   - Goal: classify the 244 queued/active tasks, separate live P0 work from old 2026-06-29 probe waves, and create a safe cancel/archive recommendation list.
   - Target nodes: `new` or `uiap` for read-only report; `main` for Control Plane repair after owner approval.
   - Guardrails: no cancellations in the first task; produce a proposed action list only.

5. `P0_FLEET_RESOURCE_GATED_DISPATCH_POLICY_2026_07_02`
   - Goal: enforce dispatch scoring that down-ranks low-memory nodes and busy nodes, and routes heavy implementation away from `main`, `mesh-9fts`, and `qjns` until resource probes are healthy.
   - Target nodes: `main` or `primary-candidate` after release/runtime blockers settle.
   - Guardrails: tests required; no live deploy without canary.

6. `P0_UIAP_LIGHT_KNOWLEDGE_WORK_STEWARD_2026_07_02`
   - Goal: use `uiap` only for light RAG/knowledge reports while its resource and exposure gates remain limited.
   - Target node: `uiap`.
   - Guardrails: no heavy models, no production service exposure, no secret indexing.

Immediate blockers to clear before claiming 20-server always-online:

- Missing canonical 20-server identity mapping.
- Stale base and mesh cards outnumber fresh usable workers.
- Several fresh nodes are busy with concurrent tasks.
- Memory pressure on small nodes limits safe MIMO/subagent fanout.
- Home/primary freshness must be repaired or explicitly classified.
- Queue retention must stop old waves from consuming operational attention.
