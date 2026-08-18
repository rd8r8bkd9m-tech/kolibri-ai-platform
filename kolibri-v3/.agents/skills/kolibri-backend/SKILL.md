---
name: kolibri-backend
description: "Kolibri V3 FastAPI backend: backend/app domain modules, thin routers, append-only migrations, backend/venv environment, and pytest conventions. Use for any backend change, migration, or API fix."
license: MIT
---

# Kolibri Backend

Работаем внутри `kolibri-v3/`. Сначала прочитать `kolibri-v3/AGENTS.md` и
`docs/PROJECT_MAP.md` (строка про `backend/app/`).

## Когда использовать

- Любое изменение backend: новый эндпоинт, фикс API, доменная логика.
- Новая миграция или изменение схемы.
- Диагностика серверной части auth/биллинга/смет/чата.

## Rules

- Домены в `backend/app/`; роутеры — только транспорт, без бизнес-правил.
- Миграции append-only; существующая выпущенная миграция не переписывается;
  изменения схемы не прятать в startup.
- Единственный venv — `backend/venv` (requirements-dev.txt); никаких `.venv`
  и родительского `backend/venv`.
- Новая подсистема/реверс зависимости/смена persistence-границы — ADR.

## Структура

- **Домены**: `chat/`, `billing/`, `estimate_*.py`, `agent_runtime.py`,
  `direct_model_runtime.py`, `identity.py`, `mobile_auth.py`, `config.py` и др.
- **Роутеры тонкие**: `*_router.py`, `main.py` — только транспорт.
- **Конфигурация**: frozen `@dataclass` + `from_env()` в `backend/app/config.py` (не Pydantic BaseSettings).
- **Безопасность мутаций**: `require_mutation_auth` в `backend/app/security.py` —
  Bearer (native mobile) или Origin + double-submit CSRF (браузер).

## Workflow

1. Определить владельца данных/контракта по `docs/SOURCE_OF_TRUTH.md`.
2. Добавить/изменить поведение в доменном модуле.
3. Тонкий эндпоинт в роутере; контракт-тесты рядом.
4. Новая миграция при изменении схемы.
5. Тесты: `PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/<file>.py -q`
   (весь набор — `-m pytest -q backend/tests`).
6. Линт: `backend/venv/bin/ruff check backend server`; компиляция: `compileall -q backend/app server`.

## Распространённые ловушки

- Мобильный auth — отдельные эндпоинты `/v1/mobile/auth/*` (access 15 мин, refresh 30 дней, ротация с детектом reuse) в `mobile_auth.py` — не смешивать с веб-сессиями.
- `GET /v1/health` (`service=kolibri-v3`, instance id) — контракт супервизора; не ломать формат.
- Новая подсистема/реверс зависимости/смена persistence-границы — требуется ADR в `docs/adr/` (шаблон `0000-template.md`).

## Verification

- `npm run verify` (backend-гейты: ruff, compileall, pytest) — обязательно после изменений.
- `npm run verify:structure` / `npm run verify:architecture` — контракты структуры.
- Живой смоук после изменения API — на работающем стеке (см. `kolibri-dev-stack`).

## Related skills

- `kolibri-estimates-engine` — сметные домены
- `kolibri-auth-session` — клиентская сторона auth
- `kolibri-billing` — биллинг и entitlements
- `fastapi` / `database-migrations` — (из внешних наборов, при необходимости)
