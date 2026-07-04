# Plan

Task: `P0_FLEET_ROLE_CAPABILITY_INVENTORY_2026_07_01`

Goal: produce a read-only fleet role and capability inventory for Kolibri
Factory, then canonicalize the useful server-generated evidence into exact
artifact paths.

Steps:

1. Query Control Plane health and node cards from the server side.
2. Classify visible node cards into owner-facing nodes, mesh shadow cards, and
   stale metadata cards.
3. Build safe target pools for implementation, review, QA, RAG, Telegram,
   observability, canary deploy, and model/LLM work.
4. Extract node blockers and next repair tasks.
5. Relay the generated output into exact `docs/agent/...` paths after the
   initial runner wrote non-contract file names.
