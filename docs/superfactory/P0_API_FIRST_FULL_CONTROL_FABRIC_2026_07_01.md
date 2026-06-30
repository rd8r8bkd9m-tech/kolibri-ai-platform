# Superfactory Contract: P0_API_FIRST_FULL_CONTROL_FABRIC_2026_07_01

This uppercase artifact preserves the required Control Plane filename for the API-first full-control Fabric work.

Canonical implementation documentation:

- `docs/fabric-api-first-control.md`
- `docs/superfactory/api-first-full-control-fabric.md`

Contract summary:

- Routine factory control is API-first through protected Fabric API contracts.
- SSH is emergency-only for bootstrap, break-glass recovery, and diagnostics.
- Unavailable targets return structured blocked envelopes with fallback routes and repair tasks.
- Owner full-control actions require authentication, authorization scopes, audit logging, and credential rotation.
- Node identity uses stable non-secret node ids and Russian display names.
- Bootstrap safe stubs accept non-secret metadata and never return secrets.

