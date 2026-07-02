# Frontend Backend Route Matrix

| frontend_call | method | expected_response | backend_exists | status | risk | action |
| --- | --- | --- | --- | --- | --- | --- |
| `/api/providers` | GET | provider list with availability | yes, `backend/main.py` | guarded | provider manager may report only MIMO or fail | show provider error and fallback `mimo` option |
| `/api/models` | GET | model catalog | yes, `backend/main.py` | not directly used | low | keep available for future selector |
| `/api/chat` | POST | assistant response JSON | yes, `backend/main.py` | guarded | backend/provider outage | show explicit chat connection error |
| `/ws/chat` | WS | streaming/non-streaming chat messages | yes, `backend/main.py` | guarded | websocket unavailable on production proxy | fallback to `/api/chat` |
| `/api/factory/status` | GET | normalized factory status, or degraded JSON | yes, `backend/main.py` | active | production proxy currently not returning FastAPI JSON | show degraded/fallback status |
| `/cluster/status` | GET | legacy cluster status | yes, alias in `backend/main.py` | intentionally unused | old frontend branches use it | keep frontend on `/api/factory/status` |
| `/api/knowledge` | GET | documents/items | proxy exists in `backend/main.py` | guarded | RAG upstream may be down or route shape may differ | show service banner and disable fake success |
| `/api/knowledge/upload` | POST | upload result | proxy exists in `backend/main.py` | guarded | RAG upstream may reject upload shape | disable upload when knowledge route is degraded |
| `/api/knowledge/search` | POST | search results/items | proxy exists via `/api/knowledge` prefix to RAG `/rag/search` | active | RAG upstream may be down | use this public route; show explicit search error |
| `/rag/search` | POST | internal RAG search | no public frontend route in `backend/main.py` | removed from frontend | production same-origin 404/proxy leak | keep only in docs as internal upstream |
| `/api/health` | GET | health JSON | yes, `backend/main.py` | production blocker | `kolibriai.ru` currently returns MikroTik `Invalid request` | fix deployment/proxy outside this branch |
| `/api/v1/ai/models` | GET | AI model list | yes, `backend/routes_v1.py` | not used by portal | duplicates `/api/models` | leave unchanged |
| `/api/v1/ai/chat` | POST | AI chat result | yes, `backend/routes_v1.py` | not used by portal | duplicate path family | leave unchanged |
| `/v1/models` | GET | OpenAI-style models | no current FastAPI route found | blocked | browser history suggests owner expected this at times | do not implement in web PR |
| `/v1/responses` | POST | OpenAI-style response | no current FastAPI route found | blocked | belongs to model/API fabric work | forbidden in this task |
| `/v1/chat/completions` | POST | OpenAI-style chat completion | no current FastAPI route found | blocked | belongs to model/API fabric work | forbidden in this task |
| `/v1/agents/tasks` | GET/POST | agent tasks | no current portal backend route found | blocked | overlaps Control Plane/agent APIs | forbidden in this task |
| `/v1/agents/status` | GET | agent status | no current portal backend route found | blocked | overlaps Control Plane/agent APIs | forbidden in this task |
| `/v1/agents/artifacts` | GET | agent artifacts | no current portal backend route found | blocked | overlaps Control Plane/agent APIs | forbidden in this task |

