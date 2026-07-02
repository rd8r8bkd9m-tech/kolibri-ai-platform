# Next

Recommended next task:

`P0_UIAP_RAG_INDEXER_CONTRACT_TESTS_2026_07_02`

Purpose:

- Add narrow tests for the future internal-only RAG indexer contract before any
  service implementation.

Required coverage:

- Health contract for internal RAG service readiness.
- Search contract shape for deterministic source, chunk, score, and staleness
  fields.
- Source allowlist and secret-like content quarantine.
- Immutable collection naming and alias-promotion failure behavior.
- Resource guard for light CPU-only indexing.

Do not do yet:

- Do not expose a public `/search` endpoint.
- Do not run large batch indexing.
- Do not store secrets in `uiap`.
- Do not send heavy builds or model-serving workloads to `uiap`.
- Do not push to `main`.

