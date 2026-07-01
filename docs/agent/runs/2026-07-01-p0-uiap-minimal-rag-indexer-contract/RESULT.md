# RESULT

Status: failed remotely with useful docs-only output; exact artifact relay
completed locally.

Control Plane result:
- task_id: `P0_UIAP_MINIMAL_RAG_INDEXER_CONTRACT_2026_07_01`
- attempt_id: `P0_UIAP_MINIMAL_RAG_INDEXER_CONTRACT_2026_07_01-attempt-1`
- lease owner: `primary-candidate:agent-host-primary`
- final state: `failed`
- failure reason: missing exact required `RESULT.md` path
- result path:
  `/var/lib/kolibri-agent/artifacts/P0_UIAP_MINIMAL_RAG_INDEXER_CONTRACT_2026_07_01/P0_UIAP_MINIMAL_RAG_INDEXER_CONTRACT_2026_07_01-attempt-1/result.json`

Useful remote output:
- GitHub source indexing flow.
- ChromaDB collection and chunking contract.
- Control Plane trigger contract.
- Future internal `/health` and `/search` contract.
- Security and resource gates.
- Remote readiness basis and risk/follow-up map.

Canonical relayed output:
- `docs/agent/intelligence/2026-07-01-uiap-rag-indexer-contract/UIAP_RAG_INDEXER_CONTRACT.md`
- `docs/agent/intelligence/2026-07-01-uiap-rag-indexer-contract/RESOURCE_AND_SECURITY_GATES.md`
- this exact run artifact set.

Key contract result:

`uiap` may become a light CPU-only RAG and skills-indexing node, but the first
implementation must stay internal and gated. Indexing must use GitHub commit
SHA as source of truth, immutable ChromaDB physical collections, deterministic
chunk IDs, staging validation before alias promotion, redacted failure events,
and Control Plane-owned authorization.

This task does not authorize:
- public `/search`;
- production service exposure;
- automatic scheduled reindex jobs;
- indexing runtime artifacts or private logs;
- heavy models or large batch indexing on `uiap`;
- product-code changes.
