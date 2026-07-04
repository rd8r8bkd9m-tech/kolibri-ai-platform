# Start Factory MVP Execution Proof

Status: `blocked`

Attempted proof path:

- `GET http://10.99.0.2:9101/v1/health`
- `GET http://10.99.0.2:9101/v1/fleet/nodes`
- `GET http://10.99.0.2:9101/v1/tasks/queue/diagnostics`
- `GET http://127.0.0.1:9101/v1/health`

Observed:

- `10.99.0.2:9101` timed out with HTTP `000` for health/fleet/queue probes.
- `127.0.0.1:9101` refused connection.
- Local `kolibri-factory-control.service` was `inactive`.

Proof result:

- `task_id`: none.
- `node`: none.
- `runner`: none.
- `artifact_path`: none.
- `artifact_collectable`: false.
- `content_bearing`: false.

Repair task:

```json
{
  "kind": "repair_control_plane_api",
  "priority": "P0",
  "constraints": ["preserve_queue", "no_destructive_commands", "no_secret_printing"],
  "success_criteria": [
    "GET /v1/health returns 200",
    "GET /v1/fleet/nodes returns nodes",
    "GET /v1/tasks/queue/diagnostics or /v1/tasks returns queue state"
  ]
}
```
