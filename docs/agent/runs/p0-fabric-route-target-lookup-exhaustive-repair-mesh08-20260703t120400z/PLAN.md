# P0 Fabric Route Target Lookup Exhaustive Repair

## Goal

Fix or prove `/v1/fabric/route` explicit `target_node` lookup so an exact node target is resolved from the authoritative node record/index instead of being constrained by bounded fallback sampling.

## Constraints

- Do not mutate live tasks.
- Do not touch provider lifecycle or secrets.
- Preserve route fallback sampling bounds.
- Preserve health vocabulary from PR #159: `online`, `ok`, `running`, and `fresh` are routable; `stale`, `degraded`, `offline`, `drained`, missing capability, and missing node are blocked with precise reasons.
- Add a focused regression for a `target_node=new`-like node outside the sampled/fallback window.

## Plan

1. Inspect the current route implementation, PR #159 relationship, and route tests.
2. Reproduce the local failure shape with a deterministic regression where the target node is outside sampled candidates.
3. Change explicit target lookup to use the authoritative node collection/index directly.
4. Keep fallback candidate sampling bounded for non-target routing.
5. Run focused tests and record outcomes.
