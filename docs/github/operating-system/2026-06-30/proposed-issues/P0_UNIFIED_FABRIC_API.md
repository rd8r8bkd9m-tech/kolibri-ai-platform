# P0 Unified Fabric API and Server Connectivity

## Context

Kolibri needs one protected API path for command nodes, Control Plane, Agent Host, models, tasks, artifacts and fallback routing.

## Scope

- API-first endpoints and schemas.
- Fleet route/status/capabilities.
- Agent task submit/status/artifacts/cancel.
- OpenAI-compatible model surface.

## Acceptance

- No dead-end `server unavailable` responses.
- Structured blocked responses include reason, fallback nodes and repair task.
- GitHub issue/PR/task links are present.

## Forbidden

- No destructive server action.
- No secret printing.
- No push to `main`.
