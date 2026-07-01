# TESTS

Validation performed:

- `python3 -m json.tool docs/agent/dispatcher/envelopes/P0_UIAP_RAG_SKILLS_REGISTRY_READINESS_2026_07_01.json`
- Control Plane POST returned `201 Created`.
- Exact Control Plane task polling showed:
  - `state=running`
  - `lease_owner=uiap:agent-host-uiap`
  - fresh heartbeat while running
- Final exact Control Plane task query showed:
  - `state=completed`
  - `result_reference=/var/lib/kolibri-agent/artifacts/P0_UIAP_RAG_SKILLS_REGISTRY_READINESS_2026_07_01/P0_UIAP_RAG_SKILLS_REGISTRY_READINESS_2026_07_01-attempt-1/result.json`

This was a read-only readiness probe. No product tests were expected.
