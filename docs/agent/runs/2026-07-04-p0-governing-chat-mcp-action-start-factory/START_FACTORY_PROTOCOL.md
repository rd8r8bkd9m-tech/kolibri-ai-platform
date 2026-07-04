# Start Factory Protocol

Owner command:

```text
СТАРТ ФАБРИКИ
```

Protocol:

1. `GET /v1/action/health`
2. `POST /v1/factory/start`
3. `GET /v1/fleet/status`
4. `GET /v1/queue/status`
5. `POST /v1/tasks/submit`
6. `GET /v1/tasks/{task_id}/status`
7. `GET /v1/tasks/{task_id}/artifacts`
8. Owner report with task id, node, runner, state, artifact path and blocker list.

Safety:

- A1/A2 actions may run when Control Plane is healthy.
- A3 requires canary and rollback.
- A4/A5 are disabled.
- Dangerous actions become approval requests.
