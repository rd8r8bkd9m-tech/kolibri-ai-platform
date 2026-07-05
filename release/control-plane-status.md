# Control Plane Status

Date: 2026-07-05

## Summary

Control Plane foundation is partially implemented through the existing FastAPI backend and Python Fabric/Superfactory sidecars. The full Calibri V1 endpoint set is not yet implemented as canonical `/v1/*` backend routes.

## Current Working Surface

- `GET /api/health`
- `GET /api/factory/status`
- Fabric sidecar contracts around `/v1/fabric/*`
- Prompt3/Fabric aliases declared in `ops/factory_control.py`
- Tested contracts in `tests/test_prompt3_fabric_api_surface.py` and Superfactory tests.

## Desired Endpoint Status

See `docs/API_COMPATIBILITY_MAP.md` for current/desired/status/next action.

## Decision

No backend rewrite was done in Phase 2. Missing endpoints are recorded as gaps to avoid breaking current runtime contracts.

## Next Safe Action

Add compatibility tests for one endpoint group at a time, starting with read-only status/agents/tasks routes.
