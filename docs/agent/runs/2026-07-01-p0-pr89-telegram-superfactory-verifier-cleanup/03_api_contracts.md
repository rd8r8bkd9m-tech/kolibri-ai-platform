# API Contracts

PR #89 Superfactory surfaces remain:

- `GET /v1/superfactory/status`
- `POST /v1/superfactory/tasks`
- `GET /v1/superfactory/tasks/{task_id}/artifacts`
- `POST /v1/tasks`
- `GET /v1/tasks`
- `GET /v1/nodes`

Covered behavior:

- task submission
- task status
- task artifacts
- node and model runner status
- PR and CI artifact links

This cleanup does not broaden the API design; it only adds the verifier alias
test path and run documentation expected by the Control Plane wrapper.
