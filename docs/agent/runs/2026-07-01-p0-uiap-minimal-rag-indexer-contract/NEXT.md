# NEXT

Recommended next task:

`P0_UIAP_RAG_INDEXER_CONTRACT_TESTS_2026_07_01`

Purpose:
- add contract tests for future `/health`, `/search`, staleness detection,
  failed promotion and secret-like content quarantine before any service code is
  implemented.

Required gates before implementation:
- approved embedding model and version pin;
- approved `docs_skills_minimal_v1` corpus profile;
- secret-like content detector selection;
- Control Plane trigger schema approval;
- resource budget for CPU, RAM, disk, ChromaDB retention and query limits;
- internal-only service identity and authorization model.

Do not start production RAG service deployment until these gates are approved.
