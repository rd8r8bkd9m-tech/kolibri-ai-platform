# TESTS: P0 API-First Full-Control Fabric

## Remote Test Evidence

Remote artifact from `P0_API_FIRST_FULL_CONTROL_FABRIC_FINALIZE_2026_07_01` reported:

- focused tests: `5 passed`
- full pytest: `65 passed, 1 warning`

Remote artifact from `P0_API_FIRST_FULL_CONTROL_FABRIC_CONTRACT_ALIGN_2026_07_01` reported:

- focused tests: `5 passed`
- full pytest: `65 passed, 1 warning`
- docs-only alignment commit

## Contract Checks

Required docs:

- `docs/superfactory/API_FIRST_CONTROL_FABRIC.md`
- `docs/superfactory/FULL_CONTROL_API_POLICY.md`
- `docs/superfactory/NODE_IDENTITY_AND_KEY_ROTATION.md`
- `docs/superfactory/API_FALLBACK_ROUTING_POLICY.md`
- `docs/superfactory/ANY_NODE_API_ACCESS_RUNBOOK.md`
- `docs/superfactory/NEW_SERVER_API_BOOTSTRAP.md`
- `docs/superfactory/ADMIN_API_SECURITY_GATES.md`
- `docs/superfactory/TASKS.md`

Required run artifacts:

- `docs/agent/runs/2026-07-01-p0-api-first-full-control-fabric/PLAN.md`
- `docs/agent/runs/2026-07-01-p0-api-first-full-control-fabric/ACTIONS.md`
- `docs/agent/runs/2026-07-01-p0-api-first-full-control-fabric/TESTS.md`
- `docs/agent/runs/2026-07-01-p0-api-first-full-control-fabric/RESULT.md`
- `docs/agent/runs/2026-07-01-p0-api-first-full-control-fabric/NEXT.md`

## Remaining Gap

The Control Plane task verifier failed previous attempts because remote agents created useful artifacts with non-canonical filenames. The branch must keep exact required names so future checks can be deterministic.
