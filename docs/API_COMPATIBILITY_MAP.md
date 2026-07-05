# API Compatibility Map

Do not remove current Fabric endpoints without compatibility tests. This branch keeps `/v1/fabric/*` and agent aliases stable while Calibri V1 endpoint names are mapped.

| Desired Endpoint | Current Contract | Status | Next Action |
| --- | --- | --- | --- |
| `GET /health` | `GET /api/health`, Fabric sidecar `/v1/fabric/health` | partial | Add alias only with smoke test. |
| `GET /v1/status` | `/api/factory/status`, Superfactory status helper | gap | Add read-only aggregate status endpoint or document Fabric equivalent. |
| `GET /v1/agents` | factory node state, `ops/agent_host.py` | partial | Normalize node/agent list response. |
| `POST /v1/agents/enroll` | bootstrap/node registration docs and Fabric contracts | gap | Add approval-aware enroll skeleton. |
| `POST /v1/agents/heartbeat` | factory node heartbeat state | partial | Add tested alias if needed. |
| `GET /v1/tasks` | Redis queue/task state in `ops/factory_control.py` | partial | Expose read-only task list compatibility route. |
| `POST /v1/tasks` | task envelope creation, `/v1/agents/tasks` alias | partial | Preserve current alias and add V1 route after tests. |
| `GET /v1/tasks/{id}` | task status/artifact helper contracts | partial | Add read-only lookup route. |
| `POST /v1/tasks/{id}/events` | dispatcher/run logs and task result updates | gap | Add event append skeleton. |
| `GET /v1/tasks/{id}/events` | logs/artifacts in run evidence | gap | Add read-only event list skeleton. |
| `POST /v1/artifacts` | artifact paths in task result envelope | partial | Add metadata-only registration skeleton. |
| `GET /v1/tasks/{id}/artifacts` | `/v1/agents/artifacts/{task_id}` alias | active alias | Keep alias; add V1 mirror after tests. |
| `POST /v1/approvals/request` | approval doctrine and admin-denied envelopes | gap | Add deny-by-default approval request skeleton. |
| `POST /v1/approvals/{id}/resolve` | owner approval doctrine | gap | Add owner-only skeleton after auth decision. |

Current tested surface: `tests/test_prompt3_fabric_api_surface.py`, `tests/test_factory_control_superfactory.py`, `tests/test_telegram_superfactory_miniapp.py`, `tests/test_telegram_superfactory_contracts.py`.
