# TESTS

Submission and remote status:

- Control Plane POST returned `201 Created`.
- Exact task polling showed:
  - `state=running`
  - `lease_owner=primary-candidate:agent-host-primary`
  - fresh heartbeats through `2026-07-01T14:02:28Z`
- Final exact task query showed:
  - `state=failed`
  - `error=command failed with rc=1: test -f docs/agent/runs/2026-07-01-p0-uiap-minimal-rag-indexer-contract/RESULT.md`
  - result reference:
    `/var/lib/kolibri-agent/artifacts/P0_UIAP_MINIMAL_RAG_INDEXER_CONTRACT_2026_07_01/P0_UIAP_MINIMAL_RAG_INDEXER_CONTRACT_2026_07_01-attempt-1/result.json`

Remote useful-output checks reported by the runner:

- `find docs/run-artifacts/P0_UIAP_MINIMAL_RAG_INDEXER_CONTRACT_2026_07_01 -type f | wc -l` -> `5`
- `find docs/intelligence/P0_UIAP_MINIMAL_RAG_INDEXER_CONTRACT_2026_07_01 -type f | wc -l` -> `2`
- `git status --short` -> only `?? docs/`

Local relay checks:

- exact run and intelligence files were created under `docs/agent/...`.
- product code was not edited.
