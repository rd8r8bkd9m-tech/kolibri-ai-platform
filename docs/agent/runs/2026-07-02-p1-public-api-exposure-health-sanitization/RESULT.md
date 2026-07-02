# P1 Public API Exposure Health Sanitization

Task: `P1_KOLIBRIAI_RU_PUBLIC_API_EXPOSURE_HEALTH_SANITIZATION_2026_07_02`

## Result

- Added a fail-closed private API auth dependency in `backend/main.py`.
- Sanitized public `GET /api/health` to return only `{"status": "ok"}`.
- Protected private API routes that expose provider, model, conversation, pipeline, factory, proxy, and `/api/v1` data.
- Added an explicit guarded `/api/v1/estimates{rest:path}` route so unauthenticated estimates requests return `401` before any business data can be exposed.
- Kept the factory status fallback as controlled JSON for authenticated callers when the control plane is unreachable.

## Auth Contract

Private routes accept either:

- `Authorization: Bearer <token>`
- `X-Kolibri-API-Key: <token>`

The token must match one of:

- `KOLIBRI_API_TOKEN`
- `KOLIBRI_ADMIN_TOKEN`
- `KOLIBRI_PRIVATE_API_TOKEN`

If no token is configured, private routes fail closed with `401`.

## QA Evidence Mapping

- `/api/v1/estimates` exposed business estimates: now guarded by explicit auth before route behavior.
- `/api/health` exposed internals such as version/database/provider details: now public minimal status only.
- `/api/factory/status` returned public 504 in QA: now unauthenticated requests are denied before control-plane fetch; authenticated upstream failures return app-owned degraded JSON.

## Non-Deployment Statement

No live runtime was deployed, restarted, or mutated for this task. Work was limited to repository code, local tests, artifacts, branch, commit, push, and draft PR.
