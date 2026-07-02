# Next

Recommended next actions:
- Route `kolibriai.ru` root to the built Kolibri frontend instead of the current inconsistent MikroTik/File Sharing response seen by `curl`.
- Repair TLS/SNI so `https://kolibriai.ru` passes certificate verification for `kolibriai.ru`.
- Wire production `/api/health`, `/api/providers`, `/api/factory/status`, `/api/chat`, `/ws/chat`, and `/api/knowledge/*` to the intended FastAPI backend.
- After deployment, run a browser hard-refresh canary on `https://kolibriai.ru/`.
- Add a production smoke that checks nonblank HTML/app shell and JSON response shape for `/api/factory/status`.

Follow-up web task:
- Add a lightweight public deployment readiness gate for `kolibriai.ru` that catches the current white-screen/cert/proxy split before owners see it.

