# PLAN

Task: `P0_UIAP_MINIMAL_RAG_INDEXER_CONTRACT_2026_07_01`

Goal: create a docs-only minimal RAG indexer contract for `uiap`, based on the
completed remote readiness probe. The contract must keep GitHub as source of
truth, route indexing through Control Plane, use ChromaDB safely, define future
internal `/health` and `/search` shapes, and avoid live production exposure
until security and resource gates are approved.

Execution model:
- Mac acts only as thin-client dispatcher.
- Remote execution runs through Control Plane and Agent Host.
- Product code, deployment config, firewall, nginx, systemd and runtime service
  changes are forbidden in this task.

Required output:
- exact five run docs;
- `UIAP_RAG_INDEXER_CONTRACT.md`;
- `RESOURCE_AND_SECURITY_GATES.md`.
