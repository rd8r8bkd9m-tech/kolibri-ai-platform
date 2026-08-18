---
name: kolibri-auth-session
description: "Kolibri authentication: mobile-session.tsx Bearer token + refresh rotation, same-origin gateway auth, session lifecycle and owner credential rules. Use when auth breaks on mobile/web, tokens expire, or session state misbehaves."
license: MIT
---

# Kolibri Auth Session

Работаем внутри `kolibri-v3/`. Сначала прочитать `kolibri-v3/AGENTS.md`.

## Когда использовать

- Auth сломан на мобильном или web: 401, токены истекают, сессия «восстанавливается» вечно.
- Меняется модель сессии, токенов или owner credential.
- Нужно понять, куда уходят запросы (origin/gateway) и почему auth не проходит.

## Модель сессии (мобильный клиент)

- Файл: `apps/kolibri-mobile/src/auth/mobile-session.tsx` (`MobileSessionProvider`).
- Статусы: `restoring | signed-out | authenticated`; `authorizedFetch` добавляет
  `Authorization: Bearer <access>`, на 401 делает ротацию refresh-токена и повторяет запрос.
- **Access-токен только в памяти** (`useRef`) — никогда в storage.
  **Refresh-токен в SecureStore** (native) / localStorage (web).
- Эндпоинты: `POST /v1/mobile/auth/login|register|refresh|logout`,
  `GET /v1/mobile/auth/session`, `PATCH /v1/profile`.
- Ответы проходят строгие валидаторы (`parseMobileUser`, `contracts.ts`) — не ослаблять.

## Same-origin через gateway (критично)

- На web (PWA через gateway `3103`) base URL = `window.location.origin` при
  cookie `kolibri_ui_client=mobile|desktop`.
- **Никогда не зашивать `http://127.0.0.1:8002` в клиент** — на телефоне этот адрес
  указывает на сам телефон, и auth ломается.
- Нативный клиент: `EXPO_PUBLIC_API_BASE_URL` (продакшн — `https://kolibriai.ru`), HTTPS обязателен (HTTP только для loopback в dev).

## Правила владельца

- **Не бутстрапить, не переименовывать, не ротировать и не перезаписывать**
  существующий credential платформенного владельца — только по явному запросу
  владельца продукта.
- Не выдумывать и не подставлять API-ключи; ключи читаются только из
  `kolibri-v3/.env.local` (whitelist в `scripts/dev-backend.sh`).

## Workflow при поломке auth

1. Определить платформу: web (gateway same-origin) или native (EXPO_PUBLIC_API_BASE_URL).
2. Проверить цепочку: логин → access в памяти → authorizedFetch с Bearer → 401 → refresh rotation.
3. Проверить, что запросы идут на правильный origin (не `8002` в проде).
4. Проверить SecureStore/localStorage: refresh не пуст, access отсутствует.
5. Проверить серверную сторону: `/v1/mobile/auth/*` (access 15 мин, refresh 30 дней, reuse-детект) в `backend/app/mobile_auth.py`.

## Verification

- `npm run mobile:typecheck`; контрактные тесты auth в `apps/kolibri-mobile/tests/`.
- Live: регистрация/логин через gateway-ориджин (`http://127.0.0.1:3103`),
  запросы на `/v1/mobile/auth/*` same-origin (см. `kolibri-v3-development` live-чеклист).
- `npm run test:qa:mobile:flow` — login → logout → login на живом стеке.

## Related skills

- `kolibri-mobile-state` — где живёт состояние сессии
- `kolibri-dev-stack` — gateway-роутинг и health
- `kolibri-backend` — серверные эндпоинты auth
