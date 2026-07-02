# Actions

- Started from clean task branch `agent/P0_EXEC_KOLIBRIAI_FACTORY_PANEL_DURABLE_BACKEND_2026_07_02/generic`.
- Confirmed existing frontend calls `/api/factory/status`.
- Confirmed existing backend has `/api/factory/status`, but the control-plane error path used HTTP 503.
- Confirmed existing nginx only had broad `/api/` proxying and no exact factory-panel route ownership.
- Public probe on 2026-07-02:
  - `https://kolibriai.ru/?telegram=1` returned HTTP 200.
  - `https://kolibriai.ru/api/health` returned HTTP 400 with generic `Invalid request.`.
  - `https://kolibriai.ru/api/factory/status` returned HTTP 400 with generic `Invalid request.`.
- Implemented durable repo changes:
  - backend route aliases and HTTP-200 degraded JSON fallback,
  - exact nginx factory status locations,
  - deploy script nginx install and rollback backup,
  - focused tests.
