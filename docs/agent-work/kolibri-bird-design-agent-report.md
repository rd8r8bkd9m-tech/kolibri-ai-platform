# Kolibri Bird Design Agent Report

Дата: 2026-06-29  
Роль: дизайн-директор птицы Kolibri  
Scope: frontend bird-related реализация и UX/implementation readiness. Control Plane/ops/backend правки не трогались.

## Итог

Текущая реализация уже движется в правильном направлении: есть `LivingKolibri` как controller-wrapper, SVG fallback работает без Rive, размеры фиксированы, `prefers-reduced-motion` учитывается в основном `KolibriBird`, а landing/app/header используют птицу как продуктовый сигнал.

GO WITH CAVEATS: птица может оставаться в текущем production fallback, но перед Rive/asset handoff нужен короткий frontend slice по единому state controller, accessibility semantics и дедупликации аватара.

## Малые правки в этом проходе

1. `frontend/src/components/KolibriBird.jsx`
   - Добавлен opt-in `ariaLabel`, чтобы semantic state мог отличаться от visual fallback state.

2. `frontend/src/components/LivingKolibri.jsx`
   - Offline визуально продолжает мапиться в `sleepy`, но получает честный label `Колибри без сети`.
   - Убран default `aria-live="polite"` с обертки. Это соответствует Rive spec: у персонажа не должно быть noisy live-region по умолчанию.

3. `frontend/src/components/LandingShell.jsx`
   - Landing dock больше не говорит `Живая птица / отражает состояние чата`.
   - Заменено на продуктовый статус: `Статус / ожидает соединение`, `слушает ввод`, `думает над ответом`, `чат готов к работе`.

4. `frontend/src/components/KolibriAvatar.tsx`
   - Исправлена опечатка в `aria-label`: `Калибри` -> `Колибри`.

## Findings

### P0. Semantic state был слабее visual mood

До правки offline приходил в `LivingKolibri` как canonical `offline`, но `KolibriBird` получал visual state `sleepy`, поэтому browser snapshot видел `Колибри спит`. Для state indicator это неверный смысл: пользователь или screen reader должны получать состояние продукта, а не только настроение fallback-анимации.

Статус: исправлено малой правкой через `ariaLabel`.

### P1. Controller есть, но state coverage пока узкий

`frontend/src/App.jsx` вычисляет только:

- `offline`, если WebSocket не подключен;
- `thinking`, если идет loading;
- `listening`, если composer в фокусе или есть input;
- `idle` в остальных случаях.

События `factory:*`, `billing:success`, `network:*` уже слушаются в `LivingKolibri`, но реальная связь с Control/factory состояниями пока не доведена до птицы через явный `taskState` или приоритетный resolver. Это не блокер текущего UI, но блокирует честный статусный характер птицы.

Рекомендация: следующим маленьким slice вынести `useKolibriCharacterController` и подключить только read-only сигналы из уже имеющегося frontend `clusterStatus`, без изменения Control Plane API.

### P1. Есть две почти одинаковые SVG-реализации

`KolibriBird.jsx` и `KolibriAvatar.tsx` дублируют SVG, labels и animation map. Сейчас build проходит, потому что TS-компоненты не входят в активный route graph, но в `MessageBubble.tsx` и `ThinkingIndicator.tsx` есть импорты `@/components/kolibri/KolibriAvatar`, тогда как фактический файл лежит в `frontend/src/components/KolibriAvatar.tsx`.

Риск: при подключении этих TS-компонентов появится broken import или divergent behavior.

Рекомендация: оставить `KolibriBird` единственным SVG fallback, а `KolibriAvatar` сделать thin wrapper или удалить после проверки call sites.

### P1. Landing использует птицу убедительно, но слишком много инстансов на первом экране

На landing одновременно видны:

- brand bird в nav;
- dock bird;
- bird в embedded app header;
- welcome bird внутри workbench.

Это не ломает layout, но снижает ощущение "один живой продуктовый индикатор". Спецификация прямо предупреждает, что landing может быть expressive, но не должен превращаться в marketing clutter.

Рекомендация: после Rive/asset slice оставить одну крупную живую птицу в hero/workbench, а nav/header в preview сделать статичным small SVG или скрыть один из повторов.

### P2. Initial offline выглядит как финальное состояние, а не boot/degraded

Без backend dev server первый экран сразу показывает offline/sleepy. Это честно для отсутствующего соединения, но UX-настроение слишком пассивное на первом визите.

Рекомендация: добавить краткий `connecting`/`booting` grace state или текстовый статус `подключается`, а `offline` включать после первой явной неудачи/retry threshold.

## Verification

Commands:

- `npm run build` в `frontend` - passed.
  - Осталось существующее предупреждение Vite: JS chunk > 500 kB.
- `npm run lint` в `frontend` - passed with 3 warnings.
  - `frontend/public/service-worker.js`: unused `error`.
  - `frontend/src/App.jsx`: missing hook deps in `useMemo`.
  - `frontend/src/components/chat/QuickActions.jsx`: fast-refresh export warning.

Browser evidence before patch:

- Desktop screenshot: `/tmp/kolibri-bird-audit/desktop-landing.png`.
- Mobile viewport screenshot: `/tmp/kolibri-bird-audit/mobile-landing-viewport.png`.
- Checked viewport: `390x844`.
- Console errors/warnings in inspected page: none.
- Horizontal overflow in inspected mobile page: false.

Note: `npx` was unavailable in this shell, so Playwright CLI was not used. In-app Browser was used instead. A post-patch browser reload timed out in the browser tool twice, so final post-patch verification is build/lint plus source-level inspection; browser viewport override was reset.

## Recommended next safe slice

1. Add `useKolibriCharacterController` with canonical priorities from `motion-bird-development-brief.md`.
2. Keep message-list avatars SVG-only, but route welcome/header/landing hero through `LivingKolibri`.
3. Add explicit `offline` SVG styling or mark, so offline is no longer visually borrowed from `sleepy`.
4. De-duplicate `KolibriBird` and `KolibriAvatar`.
5. Add a small DOM/a11y regression check for bird labels: offline must be `Колибри без сети`, reduced motion must disable loops, mobile must have no horizontal overflow.

