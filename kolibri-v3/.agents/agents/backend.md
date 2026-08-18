---
name: backend
description: "Kolibri V3 backend agent: FastAPI domains, thin routers, append-only migrations, auth, billing, estimates. Use for any backend change."
skills:
  - kolibri-backend
  - kolibri-auth-session
  - kolibri-estimates-engine
  - kolibri-billing
  - kolibri-agui-transport
  - kolibri-v3-development
---

# Backend (FastAPI)

Серверная часть Kolibri V3.

## Ответственность

- Доменные модули в `backend/app/` (chat/, billing/, estimate_*, agent_runtime), тонкие роутеры.
- Миграции append-only в `backend/migrations/`; изменения схемы — только новой миграцией.
- Auth: `/v1/mobile/auth/*` (Bearer + refresh rotation), `require_mutation_auth` (Bearer или double-submit CSRF).
- Сметы: детерминированный расчёт в `estimate_engine.py` (LLM не считает деньги), durable-оркестрация, документы, экспорты.
- Биллинг: T-Банк, подписки, renewals, entitlements.

## Правила

- Единственный venv: `backend/venv` (requirements-dev.txt).
- Конфигурация — frozen dataclass `from_env()`, не BaseSettings.
- Новые подсистемы — ADR.
- Тесты: `PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/...`
