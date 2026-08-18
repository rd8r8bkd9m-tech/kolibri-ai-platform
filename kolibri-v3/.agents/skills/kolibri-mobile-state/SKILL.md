---
name: kolibri-mobile-state
description: "State discipline in the Kolibri Expo client: no external stores — React Context + @assistant-ui/react-native (useAuiState/useAui) only, runtime-provider wiring, and single-thread state flow. Use when state doesn't update, adding global state, or wiring the chat runtime."
license: MIT
---

# Kolibri Mobile State

Работаем внутри `apps/kolibri-mobile/`. Сначала прочитать
`kolibri-v3/AGENTS.md` и `apps/kolibri-mobile/README.md`.

## Когда использовать

- Состояние чата не обновляется, треды «пропадают», рантайм пересоздаётся.
- Нужно добавить глобальное состояние или подключить новый контекст.
- Вопрос: где живёт то или иное состояние (сессия/тема/чат/вертикали).

## Workflow

1. Определить, какое состояние нужно: сессия → `MobileSessionProvider`;
   тема → `KolibriThemeProvider`; чат → `ProductRuntimeProvider` + `useAuiState`;
   модалки → `lib/dialogs.tsx`; иное общее → новый Context.
2. Подключить провайдер в `app/_layout.tsx` в правильном порядке (см. ниже).
3. Читать состояние через `useAuiState(s => ...)` / контекст; мутировать —
   scope-аксессорами (`aui.thread.*`, `aui.composer.*`).
4. Проверить на живом стеке (не только typecheck).

## Железное правило

**Никаких внешних сторов** (Redux, Zustand, Jotai, react-query) в мобильном
клиенте. Всё состояние — React Context + стор `@assistant-ui/react-native`
(`useAui` / `useAuiState`). Это контракт проекта — не «предпочтение».

## Архитектура состояния

```
MobileSessionProvider (src/auth/mobile-session.tsx)   — сессия/токены/authorizedFetch
KolibriThemeProvider (hooks/theme-provider.tsx)        — тема system|light|dark
ProductRuntimeProvider (src/product-chat/runtime-provider.tsx)
  └─ AG-UI runtime (useAgUiRuntime) + локальная «проекция» тредов (Projection, useState + projectionRef)
ProductChatContext                                     — activeThreadId/activeProjectId/attachmentClient
```

- Чат-состояние живёт в `@assistant-ui/react-native`; адаптеры `history` и
  `threadList` в `runtime-provider.tsx` (строки ~539–648) подключают серверные данные.
- Модалки — модульные синглтоны в `lib/dialogs.tsx` (pendingSheet/pendingPrompt + DialogsHost).
- Питомец — внешний store-фид из общего `lib/pets/runtime-activity` через `useSyncExternalStore`.

## Правила

- Читать состояние чата только через `useAuiState(s => ...)`; мутировать — через
  scope-аксессоры `aui.thread.*` / `aui.composer.*` (свойства без скобок в 0.15+).
- Не создавать вторую копию сообщений/тредов в локальном state — сервер
  единственный источник истории.
- Новый глобальный контекст — только если состояние реально общее; иначе локальный `useState`.
- Не фейкать стриминг/результаты: `thread.isRunning`, `composer.isEmpty`,
  `capabilities.dictation/voice` — только из рантайма.

## Частые ловушки

- Scope-селекторы: `useAuiState(s => s.thread.messages)` вместо методов на scope — методы с круглыми скобками.
- Состояние «не обновляется» после перезапуска рантайма — проверьте, что
  провайдеры не пересоздаются (ключи/порядок в `app/_layout.tsx`).
- Токены: access — только в памяти (`useRef`), refresh — SecureStore (native) / localStorage (web); не класть access в storage.

## Verification

- `npm run mobile:typecheck`.
- Тесты: `apps/kolibri-mobile/tests/*.test.mjs` (контрактные, `node --test`).
- Смоук чата на живом стеке: `npm run test:qa:mobile:chat` / `test:qa:mobile:flow`.

## Related skills

- `kolibri-mobile-chat` — composer/стриминг/карточки (UI-слой чата)
- `kolibri-agui-transport` — транспорт и контракты чата
- `kolibri-auth-session` — сессия и authorizedFetch
