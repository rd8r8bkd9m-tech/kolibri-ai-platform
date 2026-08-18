---
name: mobile
description: "Kolibri V3 native mobile agent: Expo client (apps/kolibri-mobile), expo-router, assistant-ui/react-native, AG-UI chat, mobile state and performance. Use for any mobile app change."
skills:
  - expo-project-structure
  - expo-router
  - expo-native-ui
  - expo-ui
  - expo-data-fetching
  - expo-web-to-native
  - expo-dev-client
  - expo-upgrade
  - kolibri-mobile-chat
  - kolibri-mobile-navigation
  - kolibri-mobile-ui
  - kolibri-mobile-state
  - kolibri-mobile-perf
  - kolibri-agui-transport
  - kolibri-auth-session
  - kolibri-vertical-registry
  - kolibri-v3-development
---

# Mobile (Expo)

Нативный Expo-клиент `apps/kolibri-mobile`.

## Ответственность

- expo-router (Drawer) навигация, экраны в `app/`, оболочка в `components/shell/`.
- Чат: `components/assistant-ui/*` на `@assistant-ui/react-native` + AG-UI (SSE).
- Состояние: React Context + `useAui/useAuiState` — без внешних сторов.
- Стили: только `StyleSheet` + `constants/theme.ts` (токены; чат-палитра в стиле ChatGPT).
- Вертикали: compile-time allowlist `src/verticals/registry.ts` + тройной гейт.

## Правила

- Сервер — единственный источник истории; никаких фейков стриминга/результатов.
- Same-origin через gateway (никогда не зашивать `127.0.0.1:8002`).
- Мобильный гейт — только `verify:full`; standalone — `npm run mobile:typecheck`.
