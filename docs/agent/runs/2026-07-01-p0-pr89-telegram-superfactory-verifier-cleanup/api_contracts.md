# API Contracts

This canonical run artifact summarizes the API verifier contract already
implemented in PR #89. It documents the Control Plane API surface only; it does
not change Telegram runtime behavior and does not claim live deployment.

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

This cleanup does not broaden the API design; it only adds canonical run
documentation expected by the Control Plane wrapper.
