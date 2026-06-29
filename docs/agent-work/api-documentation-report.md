# API documentation report

Дата: 2026-06-29

## Что сделано

- Создан основной артефакт `docs/API-RU.md`.
- Документация сверена по коду, а не по старым описаниям:
  - `ops/factory_control.py`;
  - `ops/kolibri-dispatch`;
  - `ops/telegram_gateway.py`;
  - `backend/main.py`;
  - `backend/routes_v1.py`;
  - `backend/billing.py`;
  - `backend/factory_status.py`;
  - `backend/desktop_control_contracts.py`;
  - `frontend/src/App.jsx`;
  - `frontend/src/config.js`;
  - `frontend/src/hooks/usePwaStatus.js`;
  - `frontend/public/service-worker.js`;
  - `tests/test_telegram_gateway.py`.

## Зафиксированные области

- Control Plane HTTP API: health, nodes, tasks, leases, lifecycle actions,
  agent messages, states, Redis/env settings.
- Telegram report CLI: `--send-report`, report metadata, owner chat id
  resolution, sanitizer, chunking and stdout event.
- Telegram task contracts: work/chat/image envelopes and env overrides.
- Billing API: plans, checkout, T-Банк notification, charge-due, token checks,
  fallback lead mode and recurrent payment flags.
- PWA/frontend contracts: API base, WebSocket host, backend calls, payment
  return query, service worker cache/fetch policy and PWA status hook.
- Desktop-control contracts: owner endpoints, worker-only endpoints, roadmap
  endpoints, facade placeholders, envelope validation and redaction.

## Важные уточнения

- `/api/desktop-control/*` сейчас не реализован как FastAPI router; это
  placeholder list в `backend/desktop_control_contracts.py`.
- `/v1/filesystem`, `/v1/tasks/<task_id>/artifacts`,
  `/v1/tasks/<task_id>/requeue`, `/v1/events` сейчас roadmap, а не текущий
  `ops/factory_control.py` API.
- `/api/knowledge*` вызывается frontend и проксируется backend на RAG upstream,
  но не является локальным FastAPI handler.
- FormulaLM/LLM эксперименты не запускались.

## Проверки

- Read-only сверка по `rg` и `sed` для backend, ops, frontend и тестов.
- Документационные изменения ограничены файлами:
  - `docs/API-RU.md`;
  - `docs/agent-work/api-documentation-report.md`.

