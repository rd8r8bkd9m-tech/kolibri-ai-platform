# Fabric API Gap Report

## Verified Live Before Branch

- `GET /v1/health`: 200.
- `GET /v1/fleet/nodes`: 200.
- `GET /v1/fleet/topology`: 200.
- `GET /v1/fleet/capabilities`: 200.
- `GET /v1/fleet/route`: 200.
- `GET /v1/models`: 200.
- `GET /v1/fabric/health`: 200.
- `GET /v1/fabric/routes`: 200.
- `GET /v1/tasks?summary=1&compact=1&limit=20`: 200 but slow.
- `GET /v1/tasks/queue/diagnostics`: 404.

## Added In This Branch

- `GET /v1/fleet/summary`
- `GET /v1/fleet/registry`
- `GET /v1/fleet/drift`
- `GET /v1/registry/validate`
- `GET /v1/tasks/queue/diagnostics`

## Still To Prove

- `POST /v1/responses` and `POST /v1/chat/completions` are safe blocked stubs until model routing is authenticated.
- `/v1/agents/artifacts/{task_id}` must be enforced as the source for completed task artifacts.

