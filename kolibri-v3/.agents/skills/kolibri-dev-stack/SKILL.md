---
name: kolibri-dev-stack
description: "Operate the Kolibri V3 local dev stack: single-stack discipline, ports 3103/8002/4104, dev:persistent lifecycle, health gates, and the verify pipeline. Use when starting or restarting the stack, diagnosing startup failures, or deciding which verification gate to run."
license: MIT
---

# Kolibri Dev Stack

Работаем внутри `kolibri-v3/`. Сначала прочитать `kolibri-v3/AGENTS.md`
(раздел «Canonical development runtime»).

## Когда использовать

- Нужно запустить/перезапустить/остановить локальный продукт.
- Стек не поднимается, порты заняты, health не проходит.
- Нужно решить, какой гейт верификации прогонять.

## Workflow

1. `npm run dev:persistent:status` — ожидаем `running/ready` (или `orphaned` → restart).
2. Рестарт только через `npm run dev:persistent:restart`.
3. После рестарта — чек-лист ниже (health, gateway, owner-сессия).
4. Перед сдачей изменений — нужный гейт: `npm run verify` (quick) / `verify:full` (полный) / `mobile:typecheck` (mobile).

## Правила запуска

- Единственный способ запустить продукт — `npm run dev` из корня V3 (supervisor `scripts/dev-stack.mjs`).
- **Никогда** не запускать напрямую `uvicorn`, `next dev`, systemd-юниты или родительский backend.
- `npm run dev:web` намеренно заблокирован — не использовать.
- Фоновый режим: `npm run dev:persistent` (screen-сессия), управление через
  `dev:persistent:status|restart|stop`, лог — `var/dev-runtime/screen.log`.

## Порты

| Порт | Кто | Назначение |
|---|---|---|
| 3103 | UI-gateway | Единая точка входа браузера (desktop и mobile через `/app`) |
| 8002 | V3 backend | FastAPI, health `/v1/health` |
| 4104 | Expo web/PWA | внутренний апстрим (через unix-сокет `var/mobile-web.sock`) |
| 3104 | Next.js | внутренний desktop-апстрим |

Порты переопределяются env (для диагностики конфликтов):
`KOLIBRI_V3_UI_PORT`, `KOLIBRI_V3_DESKTOP_INTERNAL_PORT`,
`KOLIBRI_V3_MOBILE_INTERNAL_PORT`, `KOLIBRI_V3_BACKEND_INTERNAL_PORT`.

Связка mobile: Expo наружу не выходит напрямую — `scripts/dev-mobile.mjs`
запускает `expo start` (API обязан быть на `8002`, иначе падает), а
`scripts/dev-mobile-private-bridge.mjs` слушает unix-сокет `var/mobile-web.sock`
и проксирует на 4104. `npm run dev:backend` — изолированный запуск только
backend через `scripts/dev-backend.sh`.

## После рестарта — обязательный чек-лист

1. preflight сообщает последнюю миграцию и `platform_owner=1`;
2. `GET http://127.0.0.1:8002/v1/health` → `service=kolibri-v3` + непустой development instance ID;
3. `GET http://127.0.0.1:3103/app` → HTTP 200;
4. сессия владельца (или явно авторизованный вход) доходит до серверного рабочего пространства.

Если `dev:persistent:status` показывает `screen_session=orphaned` — скрипт
восстановит сам; **не убивать процессы вручную и не запускать второй стек**
(pid-guard в `scripts/dev-stack.mjs` откажет).

## Верификация

- Быстрый гейт: `npm run verify` (structure → architecture → ruff → compileall → pytest → typecheck → node-тесты → cargo).
- Полный гейт: `npm run verify:full` (+ `next build`, мобильные typecheck/test/lint).
- Мобильный standalone: `npm run mobile:typecheck`.
- Gateway-роутинг: `npm run check:ui-gateway`; мобильный смоук: `npm run check:mobile-app` (оба требуют живой стек, в `verify` не входят).

## Related skills

- `kolibri-v3-development` — регрессионные ловушки (stale-бандлы, второй стек)
- `kolibri-mobile-qa` — проверка мобильного PWA в браузере
- `kolibri-orchestration` — планирование работы через стеки
