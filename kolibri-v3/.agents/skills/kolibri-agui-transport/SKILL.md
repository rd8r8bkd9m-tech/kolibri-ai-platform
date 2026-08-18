---
name: kolibri-agui-transport
description: "Kolibri AG-UI transport: SSE wire protocol, AG-UI events (RUN_STARTED, text-delta, RUN_FINISHED, RUN_ERROR), runtime-provider wiring, contracts in src/product-chat, and data part routing to cards. Use when chat streaming breaks, events misparse, or contracts drift."
license: MIT
---

# Kolibri AG-UI Transport

Работаем внутри `apps/kolibri-mobile/`. Сначала прочитать `kolibri-v3/AGENTS.md`.

## Когда использовать

- Стриминг чата сломан, события парсятся неверно, run отвергается.
- Меняются контракты сообщений/тредов или payload AG-UI run.
- Нужно добавить/изменить маппинг data-частей AG-UI на карточки.

## Транспорт

- Чат стримится по **HTTP SSE** (`Accept: text/event-stream`), не WebSocket:
  - старт run: `POST ${API_BASE_URL}/v1/chat/ag-ui`
    (`AG_UI_URL` в `src/product-chat/runtime-provider.tsx` ~строка 38).
  - **Восстановление истории — НЕ через SSE-replay.** Эндпоинт
    `GET /v1/chat/runs/{run_id}/events` (Last-Event-ID) существует на backend
    (chat/router.py:406), но мобильный клиент его не вызывает: тред
    загружается через `listMessages` + hydrate.
- Клиент — `HttpAgent` из `@ag-ui/client`; fetch-колбэк разрешает только URL
  `AG_UI_URL`; ответ обязан содержать заголовок `x-kolibri-run-id`, иначе run отвергается.
- Все запросы идут через `session.authorizedFetch` (mobile-session.tsx) —
  Bearer-токен добавляется автоматически.
- Протокольная версия: `AG_UI_PROTOCOL_VERSION="0.0.57"` на backend
  (estimate_generation_router.py:51) и `@ag-ui/client ^0.0.57` — при drift
  контрактов сверять именно их.
- Отмена: `agent.abortRun()` + `POST /v1/chat/runs/{run_id}/cancel`.

## Контракты

- Строгие парсеры/типы — `src/product-chat/contracts.ts` (ProductThread/Message).
- **Не импортировать `contracts/` и `generated/`** — мобильный код использует
  локальные зеркала; при расхождении контракт меняется authority-first
  (backend schema → contract tests → клиенты), см. `docs/SOURCE_OF_TRUTH.md`.
- Полезная нагрузка run: `buildMobileAgUiPayload` в `runtime-provider.tsx`
  (`threadId`, `runId`, `messages`, `tools:[]`, `context:[]`,
  `forwardedProps: {agentProfile, executionMode: standard|developer, accessMode}`).

## Карточки данных

- Маппинг AG-UI `data.by_name` → карточка — в
  `components/assistant-ui/message.tsx:182-192` (by_name + Fallback);
  `src/product-chat/cards.ts` содержит только `DATA_PART_NAMES` и парсеры
  данных карточек (cards.ts:9-12). Рендеры — `components/assistant-ui/cards/`.
- **Мобильный allowlist данных ограничен**: weather и image-generation;
  остальные типы (в т.ч. сметные data-карточки) на мобильном не рендерятся —
  показывается Fallback-карточка, никогда не краш.

## Rules

- Никаких вторых текстовых состояний: стриминг/результаты — только реальные
  AG-UI события от сервера, без локальных фейков.
- `contracts/` и `generated/` не импортировать — локальные зеркала, контракт
  меняется authority-first (см. `docs/SOURCE_OF_TRUTH.md`).
- Неизвестный тип data-части — Fallback-карточка, не краш.

## Workflow

1. Проверить, что запрос уходит на правильный origin (same-origin через gateway, не захардкоженный `8002`).
2. Проверить события: `RUN_STARTED` → text-delta → `RUN_FINISHED` (не `RUN_ERROR`).
3. Проверить заголовок `x-kolibri-run-id` в ответе.
4. Сверить контракт парсера с фактическим payload (backend schemas).
5. Воспроизвести на живом стеке свежим пользователем (не QA-сессией).

## Verification

- Backend-тесты транспорта: `backend/tests/` (chat/AG-UI); мобильные контракты —
  `apps/kolibri-mobile/tests/` (в т.ч. `native-vertical-contracts.test.mjs`, проверяет AG-UI payload).
- Live: `npm run test:qa:mobile:flow` (стриминг → reload → история сохраняется).

## Related skills

- `kolibri-mobile-chat` — composer/стриминг UI (верхний слой)
- `kolibri-mobile-state` — как состояние связано с рантаймом
- `kolibri-backend` — серверная сторона `/v1/chat`
- `streaming` (assistant-ui) — протокол assistant-stream
