# CONTROL_GATEWAY_STATUS

`gateway_file`: `ops/chatgpt_action_gateway.py`

`status`: working locally as a thin HTTP adapter; not production-deployed in this task.

Implemented endpoints:

- `GET /v1/action/health`
- `POST /v1/factory/start`
- `POST /v1/director/tick`
- `GET /v1/fleet/status`
- `GET /v1/queue/status`
- `POST /v1/tasks/submit`
- `GET /v1/tasks/{task_id}/status`
- `GET /v1/tasks/{task_id}/artifacts`
- `GET /v1/github/prs`
- `POST /v1/approvals/request`

Every endpoint returns the action envelope fields:

- `status`
- `request_id`
- `task_id`
- `control_plane_used`
- `artifacts`
- `blocked_reason`
- `fallback_nodes`
- `repair_task`
- `next_action`

Dangerous requests are converted into approval requests and are not sent to Control Plane.
