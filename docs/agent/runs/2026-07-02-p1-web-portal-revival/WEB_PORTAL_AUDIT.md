# Web Portal Audit

Current code source:
- `frontend/` is the only frontend application present on `origin/main`.
- `remote/kolibriai-frontend/` and `landing/` are not present on `origin/main`.
- The current app is React/Vite and contains chat, documents, search, and factory status views.

Current production reference:
- `kolibriai.ru` is the product target for this task.
- Yandex Browser initially displayed a minimal Kolibri chat shell:
  - bird avatar
  - "Чем могу помочь?"
  - "Спросите Колибри..."
  - action chips for estimate, contract, report, and data analysis
  - footer text about checking important AI output
- Hard refresh in Yandex produced a blank white screen.
- `curl` sees TLS/SNI/content mismatch:
  - certificate hostname mismatch for `kolibriai.ru`
  - `curl -k https://kolibriai.ru/` returns MikroTik File Sharing HTML
  - `curl -k https://kolibriai.ru/api/health` returns `{"error":"Invalid request."}`

Frontend findings:
- Chat used `/api/chat` fallback and `/ws/chat`.
- Factory status used `/api/factory/status`.
- Documents used `/api/knowledge` and `/api/knowledge/upload`.
- Search previously called direct `/rag/search`, which is not a public route in `backend/main.py`.
- Provider fetch errors were silent.
- Document/search upstream outages showed generic empty states.

Backend findings:
- `backend/main.py` exposes `/api/health`, `/api/providers`, `/api/models`, `/api/chat`, `/ws/chat`, `/api/factory/status`, and `/cluster/status`.
- `/api/knowledge*` is proxied to the RAG service with `/api/knowledge` stripped and `/rag` added.
- Direct `/rag/search` is not a public frontend route.
- `backend/routes_v1.py` exposes `/api/v1/ai/*` and `/api/v1/swarm/*`, not the OpenAI-style `/v1/*` surface.

Remote artifacts reviewed:
- FE V3 shell: useful welcome screen language and component direction; not copied wholesale because it contains older `/cluster/status` usage.
- Public proxy chat contract: useful same-origin websocket/API approach; current main already follows most of it.
- Older `kolibriai.ru` branch: useful as history, but not selected as source because it has outdated websocket host assumptions.

