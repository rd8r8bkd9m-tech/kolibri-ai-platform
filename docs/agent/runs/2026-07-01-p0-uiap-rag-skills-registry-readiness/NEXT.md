# NEXT

Next recommended task:

`P0_UIAP_MINIMAL_RAG_INDEXER_CONTRACT_2026_07_01`

Purpose:
- define a minimal RAG indexer contract for Markdown docs and skills metadata;
- keep GitHub as source of truth;
- keep Control Plane as the dispatcher;
- keep `uiap` as a light CPU-only RAG node;
- avoid long-running production workers until a service/health/security gate is
  reviewed.

Suggested constraints:
- server execution required;
- target `uiap` or healthy RAG/knowledge node;
- no secrets;
- no production service exposure;
- no heavy models;
- no large batch indexing;
- no push to `main`;
- create exact `PLAN/ACTIONS/TESTS/RESULT/NEXT` artifacts.

Blocked items:
- Heavy RAG/model serving on `uiap` is blocked by RAM/CPU limits.
- Production RAG API exposure is blocked until auth, health, resource limits and
  observability are specified.
