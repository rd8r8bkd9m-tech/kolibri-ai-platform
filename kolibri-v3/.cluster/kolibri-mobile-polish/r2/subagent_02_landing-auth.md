# Аудит: лендинг + экран входа (Kolibri V3)

READ-ONLY код-аудит. Файлы: `components/public-site/landing/*`, `components/public-site/styles/*`,
`components/kolibri-shell/auth-panel.tsx`, `app/page.tsx`, а также затронутые в прошлом раунде
`estimate-editor.tsx`, `catalog-autocomplete.tsx`, `estimate-document-common.tsx`, `ui/class-names.ts`, `app/globals.css`.

---

## 1. Согласованность правок прошлого раунда

### ✅ Подтверждены и согласованы

| Правка | Где | Статус |
|---|---|---|
| `items-start` + safe-area + `sm:items-center sm:pt-0 sm:pb-0` | `auth-panel.tsx:315` | OK — на десктопе центрирование не съехало: `sm:items-center` перекрывает `items-start` с ≥640px, `sm:pt-0 sm:pb-0` снимают мобильные отступы |
| глазок `w-11` + `-inset-y-0.5` (×2), `pr-11` (×2) | `auth-panel.tsx:183,190,267,274` | OK — кнопка 44×44, `-inset-y-0.5` расширяет её на 2px за края инпута h-10, `pr-11` освобождает 44px под текстом |
| подзаголовок `text-foreground/70` | `auth-panel.tsx:97` | OK |
| селекты `text-base min-[960px]:text-sm` + `w-full min-w-0` (×2) | `estimate-editor.tsx:626,673` | OK — на десктопе (≥960px) возвращается `text-sm`, не выросли |
| сумма `min-w-0 break-words` | `estimate-editor.tsx:401` | OK |
| дропдаун `bottom-full top-auto min-[960px]:top-full` | `catalog-autocomplete.tsx:140` | OK — на мобиле открывается вверх, на десктопе вниз (`min-[960px]:bottom-auto min-[960px]:mt-1 min-[960px]:mb-0` корректно сбрасывают) |
| scroll-to-bottom `size-11 md:size-9` | `class-names.ts:109` | OK |
| reasoning `wrap-break-word` | `class-names.ts:175` | OK |
| `.aui-button-icon` 44px ≤959px | `globals.css:1882` | OK — правило не в `@layer` (Tailwind v4), поэтому перебивает `size-6` из `TooltipIconButton`. Таргет только этот компонент |
| hero-lead `--klp-text-soft` | `landing-copy.css:498` | OK |
| `.kp-public-shell a.klp-hero-link` | `landing-copy.css:545` | OK |
| chips/menu/send 44px | `landing-copy.css:2146,388,876` | OK (`min-height:2.75rem` / `2.75rem` / `2.75rem`) |
| `.klp-diff code span` `pre-wrap` + `overflow-wrap:anywhere` | `landing-copy.css:1439-1440` | OK |
| stage-topbar wrap + скрытие status/dots ≤640px | `landing-copy.css:2752-2760` | OK |

### ⚠️ Найденные несоответствия

**N1 (med) — 3 селекта остались `text-base` без десктоп-сброса.**
В `estimate-editor.tsx` селекты получили `min-[960px]:text-sm`, а в двух других файлах — нет:

- `estimate-document-common.tsx:324` и `:553`:
  `className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-base outline-none ..."` (без `min-[960px]:text-sm`)
- `catalog-autocomplete.tsx:155` (селект «Тип новой позиции»):
  `className="h-8 rounded-md border border-input bg-background px-2 text-base outline-none ..."` (без `min-[960px]:text-sm`)

Ответ на вопрос «не выросли ли на десктопе»: в `estimate-editor.tsx` — нет; а эти три селекта на десктопе рендерятся 16px против 14px у соседних `Input` (`inputBase = "… text-base … md:text-sm"`, `class-names.ts`). Видно в панелях «Клиент/Подрядчик» и «Повторить для другого клиента».
**Фикс:** дописать `min-[960px]:text-sm` (в `catalog-autocomplete.tsx:155` — селект в дропдауне, но тоже показывается на десктопе).

**N2 (low) — разнобой брейкпоинтов `md:` vs `min-[960px]`.**
`inputBase` использует `md:text-sm` (768px), а селекты `estimate-editor.tsx` — `min-[960px]:text-sm` (960px). В диапазоне 768–959px инпуты 14px, селекты 16px. Мелкая нестыковка на планшетах.
**Фикс:** унифицировать брейкпоинт (либо `md:text-sm`, либо `min-[960px]:text-sm` во всех местах).

---

## 2. Оставшиеся мобильные проблемы (лендинг + вход)

### M1 (med) — Экран входа не скроллится, контент может обрезаться снизу
- `components/kolibri-shell/auth-panel.tsx:315`
  ```
  <div className="relative flex h-dvh min-h-0 items-start justify-center overflow-hidden bg-background px-4 pt-[max(3rem,env(safe-area-inset-top))] pb-[max(2rem,env(safe-area-inset-bottom))] sm:items-center sm:pt-0 sm:pb-0">
  ```
  `h-dvh` + `overflow-hidden` + `items-start` (на мобиле) без скролл-контейнера. Форма регистрации (Имя/Email/Пароль + подсказка «Минимум 12 символов» + возможная ошибка + кнопка) ≈ 535px; с `pt≥48px` + `pb≥32px` на коротких вьюпортах (< ~620px, напр. iPhone SE 568px, или при открытой экранной клавиатуре, когда `dvh` схлопывается) кнопка «Создать аккаунт» и низ формы уезжают за край и недоступны. На десктопе `sm:items-center` в коротком окне обрежет и верх, и низ.
  **Фикс:** заменить на скроллируемый контейнер, напр. `h-dvh overflow-y-auto` + `min-h-0` у внутреннего блока, или `min-h-dvh` вместо `h-dvh` и убрать `overflow-hidden`/добавить `overscroll-contain`. Safe-area отступы оставить.

### M2 (med) — Низкий контраст `--klp-fainter` для мелкого текста
- `landing-copy.css:54`: `--klp-fainter: #57534f;`
  Используется для мелкого текста:
  - `.klp-pricing-toggle-note` (`:2674`, `font-size:0.78rem`)
  - `.klp-trace-chip.is-queued` (`:2383`)
  - `.klp-int-status.is-soon` (`:2562`)
  - `.klp-agent-log li i` (`:2425`)
  Контраст ≈ 2.5:1 на фоне `#111113` (`--klp-bg-soft`) — ниже WCAG AA (4.5:1 для обычного текста). Применимо ко всем вьюпортам, на мобиле особенно заметно в ярком свете.
  **Фикс:** поднять `--klp-fainter` до ~`#8a8580` или использовать `--klp-muted` (#a5a19b) для этих подписей.

### L1 (low) — Тач-цели <44px в мобильном меню
- `landing-copy.css:426` `.klp-mobile-panel a` — `padding: 0.65rem 0.8rem; font-size:0.86rem` → высота ≈ 41px.
- `landing-copy.css:2708` `.klp-mobile-cta` — `padding: 0.65rem 1rem` → ≈ 41px.
  Сам бургер (`summary`, 2.75rem) уже 44px, а ссылки внутри панели — чуть ниже нормы.
  **Фикс:** добавить `min-height: 2.75rem; display:inline-flex; align-items:center` обеим.

### L2 (low) — Селект в дропдауне каталога: 32px и плотный текст
- `catalog-autocomplete.tsx:155` — селект `h-8` (32px) с `text-base` (16px). Тач-цель <44px и текст тесноват в 32px. (Дополнительно — отсутствие `min-[960px]:text-sm`, см. N1.)
  **Фикс:** `h-9`/`min-h-11` на мобиле + `min-[960px]:h-8 min-[960px]:text-sm`.

### L3 (low) — Верхний отступ hero может не перекрывать fixed-нав на «чёлочных» телефонах
- `landing-copy.css:79` `.klp-nav { position: fixed; ... padding-top: env(safe-area-inset-top); }`
- `landing-copy.css` (media ≤640px) `padding-top: 6.5rem` (=104px).
  При `viewport-fit:cover` (`app/layout.tsx`) `env(safe-area-inset-top)` ≈ 44–59px; суммарная высота шапки ≈ 68px+47px ≈ 115px > 104px → бейдж hero может частично уходить под нав.
  **Фикс:** `padding-top: calc(6.5rem + env(safe-area-inset-top, 0px))` в media ≤640px.

### L4 (low) — Иконка «Редактировать» теперь всегда видна на десктопе
- `class-names.ts:193` `threadUserActionEdit` — удалены `opacity-0 … group-hover/user:opacity-100 focus-visible:opacity-100`.
  Мобильный фикс оправдан (на таче нет hover), но побочно на десктопе карандаш виден постоянно у каждого сообщения (раньше — по наведению). Если нужен прежний hover-режим на десктопе — вернуть через `min-[960px]:opacity-0 min-[960px]:group-hover/user:opacity-100 min-[960px]:focus-visible:opacity-100`.

### L5 (low) — `.aui-button-icon` 44px может раздвинуть action-bar на узких экранах
- `globals.css:1882` + `tooltip-icon-button.tsx:32`. Кнопки действия (copy/edit, prev/next-ветки) на мобиле становятся 44px каждая (были 24px). В строке из 3–4 кнопок на 390px возможен перенос/переполнение. Проверить визуально; при необходимости ограничить `gap`/дать `flex-wrap`.

---

## Итог по ключевым вопросам

1. **Центрирование auth на десктопе** — не сломано (`sm:items-center` работает).
2. **Селекты на десктопе** — `estimate-editor.tsx` в порядке; **3 селекта** (`estimate-document-common.tsx` ×2, `catalog-autocomplete.tsx` ×1) остались `text-base` без `min-[960px]:text-sm` и на десктопе выросли до 16px (N1).
3. **Дропдаун catalog на десктопе** — корректен, вверх не уходит (`min-[960px]:top-full`).
4. **Главные оставшиеся проблемы:** не скроллируемый экран входа (M1, риск обрезки), низкий контраст `--klp-fainter` (M2), мелочи по тач-целям и safe-area (L1–L3).
