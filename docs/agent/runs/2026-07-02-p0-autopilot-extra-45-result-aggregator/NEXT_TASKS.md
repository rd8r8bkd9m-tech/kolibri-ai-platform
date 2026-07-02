# Next Exact Tasks

1. `P0_DEPLOY_FACTORY_ROUTE_FRESHNESS_GATE_CANARY_2026_07_02`
   - Deploy only the route freshness / primary heartbeat fix through owner-approved preflight.
   - Required proof: rollback artifact, service health, `/v1/fleet/nodes`, stale primary classification fixed.

2. `P0_DEPLOY_QUEUE_GUARDIAN_BACKLOG_ENDPOINTS_2026_07_02`
   - Deploy queue guardian and backlog audit endpoints.
   - Required proof: `/v1/tasks/backlog/audit` no longer returns 404, deadletter/requeue policy output is bounded and non-destructive.

3. `P0_FACTORY_STATUS_PUBLIC_EDGE_TLS_ROUTING_REPAIR_2026_07_02`
   - Repair public edge TLS/HTTP routing for `kolibriai.ru/api/factory/status`.
   - Required proof: strict HTTPS succeeds without `-k`, backend adapter canary stays fast, no Bot API mutation.

4. `P0_QJNS_READONLY_REVIEW_CANARY_2026_07_02`
   - Run a real read-only review canary on `qjns`.
   - Required proof: clone/checkout succeeds, no push, no product mutation, artifact pack includes exact five files plus remote result.

5. `P0_AUTOPILOT_25_WAVE_CANONICAL_ARTIFACT_RELAY_2026_07_02`
   - Relay/canonicalize missing artifacts for completed branches that have code-only or envelope-only results.
   - Required proof: every wave row has exact `PLAN.md`, `ACTIONS.md`, `TESTS.md`, `RESULT.md`, `NEXT.md`, and `REMOTE_RESULT.json` or an explicit `artifact_missing_by_design` marker.

6. `P0_OWNER_REVIEW_PR113_THEN_PR109_PR112_2026_07_02`
   - Continue release-train review in the order recommended by the release steward.
   - Required proof: PR check-run state inspected, no merge to main by agents, owner decision packet updated.

7. `P0_UIAP_RAG_INDEXER_CONTRACT_TESTS_2026_07_02`
   - Add the UIAP RAG contract tests before any service implementation.
   - Required proof: health/search/staleness/failed-promotion/secret-quarantine tests exist and run without exposing production data.
