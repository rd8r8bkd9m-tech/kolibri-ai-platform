# Control Plane Agent Model

This branch currently implements Fabric/Superfactory API-first control through Python ops services.

```text
User / Lead Operator
        ↓
Fabric / Factory Control API
        ↓
Task Registry / Redis State / Logs / Artifacts / Approvals
        ↓
Worker Agents
        ↓
Artifacts / Logs / Status back to Control Plane
```

## Current Contracts

- `ops/factory_control.py` owns task envelope creation, task state, node state, Mini App envelope handling, Fabric API routes, and Superfactory status.
- `ops/telegram_superfactory.py` owns Telegram init data validation, receiver planning, runner policy, and runner selection.
- Tests covering the current Superfactory slice:
  - `tests/test_factory_control_superfactory.py`
  - `tests/test_telegram_superfactory_miniapp.py`
  - `tests/test_telegram_superfactory_contracts.py`

## Worker Agent Rule

Worker agents must use API contracts. SSH is not a worker-agent control plane.

## Desired Calibri V1 Endpoint Shape

```text
GET  /health
GET  /v1/status
GET  /v1/agents
POST /v1/agents/enroll
POST /v1/agents/heartbeat
GET  /v1/tasks
POST /v1/tasks
GET  /v1/tasks/{id}
POST /v1/tasks/{id}/events
GET  /v1/tasks/{id}/events
POST /v1/artifacts
GET  /v1/tasks/{id}/artifacts
POST /v1/approvals/request
POST /v1/approvals/{id}/resolve
```

Map current Fabric routes into this shape gradually. Do not break current `/v1/fabric/*` contracts without compatibility docs and tests.
