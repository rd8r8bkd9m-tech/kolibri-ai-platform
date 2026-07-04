# MCP Action Gateway Spec

Base URL: deployment-specific.

Auth:

- Header: `Authorization: Bearer <KOLIBRI_CHATGPT_ACTION_TOKEN>`.
- Production must set `KOLIBRI_CHATGPT_ACTION_TOKEN`.

Endpoints:

- `GET /v1/action/health`
- `POST /v1/factory/start`
- `POST /v1/director/tick`
- `GET /v1/fleet/status`
- `GET /v1/queue/status`
- `POST /v1/tasks/submit`
- `GET /v1/tasks/{task_id}/status`
- `GET /v1/tasks/{task_id}/artifacts`
- `POST /v1/approvals/request`

Danger policy: dangerous content returns `approval_required` and is not proxied.
