---
name: kolibri-mobile-perf
description: "Performance for the Kolibri Expo client: FlatList chat scroll metrics, re-render storms, bundle size, Metro cache, and memory on web/native. Use when chat scroll stutters, UI janks, bundles grow, or Metro rebuilds lag."
license: MIT
---

# Kolibri Mobile Performance

Работаем внутри `apps/kolibri-mobile/`. Сначала прочитать `kolibri-v3/AGENTS.md`.

## Когда использовать

- Скролл чата дёргается, UI «тормозит», рендеры лишние.
- Бандл растёт или Metro пересобирает дольше обычного.
- Изменения в чат-списке, анимациях или тяжёлых экранах.

## Известные ловушки (проверено на регрессиях)

1. **`FlatList.scrollToEnd` имеет устаревшие cell-метрики**, а список сбрасывает
   `scrollTop` в 0 на ре-рендер (RN-web). Для автоскролла чата скроллить хост-ноду
   напрямую: `getScrollableNode().scrollTop = node.scrollHeight` внутри двойного
   `requestAnimationFrame`, с проверкой «внизу ли пользователь».
2. **`pointerEvents: "box-none"` сломан на react-native-web** (0.21.x даёт
   невалидный CSS → fallback `auto`): полноэкранный absolute-обёртка с `box-none`
   глотает все wheel/touch-события. На web — `pointerEvents: "none"` на обёртке,
   интерактивным детям — `auto`.
3. **Re-render storms**: не мемоизировать без доказанной причины; тяжёлые списки —
   `React.memo` на уровне элемента, ключи стабильные.
4. **Metro-кэш**: устаревший бандл выглядит как «код не применился» — чистить
   кэш/перезапускать Metro, проверять маркер свежего бандла
   (`__KOLIBRI_MOBILE_ENTER_SEND__` в QA-скриптах), а не только typecheck.
5. **Бандл**: `metro.config.js` расширяет `watchFolders` на корень воркспейса —
   следить, чтобы импорты из `lib/pets` не тащили лишнее; избегать новых крупных
   зависимостей без оценки размера.

## Workflow

1. Измерить до изменений: профиль рендера (React DevTools / why-did-you-render по необходимости), размер бандла (`npx expo export` в CI-режиме, `verify:full` собирает).
2. Найти узкое место: скролл → проверка host-ноды; джанк → перерендеры/анимации; память → утечки подписок.
3. Применить точечный фикс, измерить снова.
4. Прогнать регрессионные тесты скролла (`mobile-chat-scroll.test.mjs`) и live-смоук.

## Rules

- Не оптимизировать без измерения.
- Не менять архитектуру ради перфа без необходимости.
- Анимации — только через reanimated/worklets; избегать JS-driven анимаций на главном потоке.

## Verification

- `npm run mobile:typecheck`; `node --test tests/mobile-chat-scroll.test.mjs` (из `apps/kolibri-mobile`).
- Live: `npm run test:qa:mobile:chat` (скролл вверх/вниз, автоскролл к новому сообщению).
- Полный мобильный гейт: `npm run verify:full`.

## Related skills

- `kolibri-mobile-chat` — скролл и композер чата (UI-слой)
- `kolibri-mobile-qa` — пиксельные и поведенческие проверки
- `expo-upgrade` / `expo-project-structure` — официальные Expo-скиллы (из установленного пака)
