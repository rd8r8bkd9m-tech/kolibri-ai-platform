# UX-ревизор chat-first

Дата проверки: 2026-06-29  
Агент: UX-ревизор chat-first  
Область: `frontend` React/Vite, маршруты `/` и `/app`, `ChatComposer`, `ControlFab`, `ControlPanel`, русские тексты, mobile ergonomics.

## Короткий вердикт

Merge пока нельзя считать готовым для chat-first UI. Архитектурная база хорошая: `ChatWorkspace` переиспользуется между `/` и `/app`, `ControlPanel` питается от `controlPlugins`, а Vite build проходит. Но есть два P0 перед merge:

1. На mobile 390px виден горизонтальный overflow: обрезаются header/model select, subtitle, composer и Control FAB.
2. `/` при свежем рендере оказывается проскролленным ниже начала hero, вероятно из-за общего `messagesEnd.scrollIntoView` внутри встроенного chat preview.

## Что проверено

- Архитектура `App.jsx`: ручной route split `/` vs `/app`, общий chat state, общий `ControlFab`/`ControlPanel`, shared `chatProps`.
- Компоненты: `LandingShell`, `AppHeader`, `ChatWorkspace`, `ChatComposer`, `QuickActions`, `ControlFab`, `ControlPanel`, панели Control.
- CSS responsive слой: `100svh/100dvh`, sticky composer, mobile sheet, FAB offsets, landing workbench.
- Русские тексты и смешение терминов: `Контрол`/`Control`, `Фабрика Колибри`/`Kolibri AI`, `биллинг`, `GB RAM`, `PWA`.
- Runtime smoke: `/` и `/app` отдаются Vite dev server как SPA routes.

## Evidence

- `npm run build`: passed. Есть warning по chunk > 500 kB.
- `npm run lint`: passed with warnings:
  - `frontend/public/service-worker.js`: unused `error`.
  - `frontend/src/App.jsx`: `useMemo` missing deps.
  - `frontend/src/components/chat/QuickActions.jsx`: Fast Refresh warning из-за экспорта `DEFAULT_QUICK_ACTIONS`.
- `npm run test:mobile-layout`: passed.
- `curl -I http://127.0.0.1:5174/`: `200 OK`.
- `curl -I http://127.0.0.1:5174/app`: `200 OK`.
- Chrome headless screenshots saved outside repo:
  - `/tmp/kolibri-ux-chat-first-review/01-landing-desktop.png`
  - `/tmp/kolibri-ux-chat-first-review/02-app-desktop.png`
  - `/tmp/kolibri-ux-chat-first-review/03-app-mobile.png`
  - `/tmp/kolibri-ux-chat-first-review/04-landing-mobile.png`

Limit: Control Panel screenshot via CDP did not open a debugging endpoint in this environment, so Control Panel findings are code-grounded plus FAB-visible screenshot evidence. Backend was not running, so provider/status states were observed in fallback/loading mode.

## P0

### P0-1: Mobile horizontal overflow clips critical controls

Evidence: `03-app-mobile.png` at 390x844 shows clipped model select, clipped welcome subtitle, clipped composer placeholder, and only part of Control FAB. `04-landing-mobile.png` shows the same FAB clipping and content clipped on the right.

Likely sources:

- `AppHeader` keeps `header-left` and `header-right` in one row without enough shrink/overflow strategy: `frontend/src/components/AppHeader.jsx`.
- Mobile CSS only reduces `.model-select` to `max-width: 118px`, while header still needs logo, title, subtitle, select and settings button in 390px: `frontend/src/App.css`.
- `ControlFab` has mobile `min-width: 112px` and fixed right offset; screenshot shows it can still be partially outside the visible viewport.
- `ChatComposer` placeholder is long and the input area does not prove a no-overflow invariant on narrow widths.

Acceptance before merge:

- At 360x740, 390x844, 430x932, 768x1024: `document.documentElement.scrollWidth <= window.innerWidth`.
- Header controls remain reachable; model select is either compacted, moved, or visually clipped with an intentional accessible label, not cut off by viewport.
- Control FAB is fully visible and tappable, with a minimum 44x44 target.
- Composer is fully visible; send button is visible; placeholder does not cause horizontal overflow.
- Add a real viewport guard, not only CSS regex checks, for `/app` and `/`.

### P0-2: Landing can open below the hero

Evidence: `01-landing-desktop.png` and `04-landing-mobile.png` both start around the embedded workbench/workflow area instead of the top hero/nav/H1. This breaks the first viewport promise for `/`.

Likely source:

- `App.jsx` always runs `messagesEnd.current?.scrollIntoView({ behavior: "smooth" })` on `messages`, and the same `messagesEndRef` is passed into the embedded landing `ChatWorkspace`.
- `LandingShell` embeds the actual `ChatWorkspace` preview, so the chat autoscroll can affect the landing scroll container.

Acceptance before merge:

- Fresh `/` load shows brand/nav, `Kolibri AI` H1, lead copy, primary CTA, and a visible hint of the product preview.
- `.landing-main.scrollTop` remains `0` after initial mount with empty messages.
- Chat autoscroll still works inside `/app` message list after sending/receiving messages.
- Landing preview does not steal page scroll when there are no messages.

## P1

### P1-1: Control Panel is a dialog visually, but not focus-safe yet

`ControlPanel` has `role="dialog"`, `aria-modal="true"` and Escape close, which is a good start. It does not move focus into the panel, trap focus, mark background inert, or restore focus to the FAB on close.

Acceptance:

- Opening Control moves focus to close button or active tab.
- Tab/Shift+Tab stay inside the dialog while open.
- Escape and close button return focus to Control FAB.
- Screen reader announces dialog title and current section.

### P1-2: Control tabs need accessible tab semantics

The tab row is currently a list of buttons. That is usable by mouse, but screen reader and keyboard expectations are weaker than a real tab pattern.

Acceptance:

- Tabs use `role="tablist"`, `role="tab"`, `aria-selected`, and each panel uses `role="tabpanel"` or an equivalent accessible segmented-control pattern.
- Arrow keys or clearly documented Tab navigation works across sections.
- Active section is announced.

### P1-3: `App.jsx` is carrying too many product contracts

`App.jsx` currently owns route state, API calls, WebSocket lifecycle, billing form, documents, search, cluster, theme/PWA, Control state, composer focus, and payment query handling. This is still workable for a two-route MVP, but the lint warning on `pluginContext` missing deps is a signal that state contracts are becoming fragile.

Acceptance:

- Before adding more Control plugins, extract stable hooks or controllers for chat transport, billing, knowledge, cluster, and route shell state.
- `npm run lint` has no `react-hooks/exhaustive-deps` warning in `App.jsx`.
- `controlPlugins` receives stable, typed-ish context contracts; plugin render functions do not depend on stale handlers.

### P1-4: Composer state needs stronger mobile behavior

The composer supports Enter-to-send and Shift+Enter newline, but the visible UI does not explain multiline behavior, and textarea height is imperatively adjusted only on `input`. After send, a previously tall textarea can remain visually tall until another input event.

Acceptance:

- Textarea height resets after send and after quick action prompt changes.
- Multiline entry remains comfortable on mobile keyboard.
- Loading state does not trap the user without a visible cancel/retry path if the backend stalls.

### P1-5: Billing default state can look like a form without a selected product

If `/api/billing/plans` fails or returns empty, `BillingPanel` renders the form and `Т-Банк` pill without a clear empty/configuration state. For a paid flow this needs more reassurance.

Acceptance:

- Empty plans state says whether billing is unavailable, loading, or configured without public plans.
- The primary action copy matches the state: request, checkout, retry, or disabled.
- Errors from checkout are phrased in user-safe Russian and do not expose raw backend detail.

## P2

### P2-1: Russian product language needs one glossary

Current UI mixes `Фабрика Колибри`, `Kolibri AI`, `Контрол`, `Control`, `биллинг`, `PWA`, `GB RAM`. Some terms are fine for technical users, but they should be intentional.

Acceptance:

- Define glossary: product name, Control/Контрол, billing/подписки, factory/фабрика, PWA wording.
- Landing and `/app` use the same product naming hierarchy.
- Technical metrics keep units, but user-facing labels explain why they matter.

### P2-2: Typo risk in parallel avatar component

`frontend/src/components/KolibriAvatar.tsx` has `aria-label` with `Калибри`, while the visible route currently uses `KolibriBird` with `Колибри`. It is not blocking current `/app`, but it is a component-library footgun.

Acceptance:

- All avatar components use `Колибри`.
- Run a text grep for visible Russian labels and aria labels before release.

### P2-3: Desktop `/app` uses a lot of empty vertical space

`02-app-desktop.png` looks calm and premium, but the working chat starts far from the composer. For repeated operational use, the first screen could expose recent tasks, document context, or a clearer first next action without becoming a landing page.

Acceptance:

- Keep the quiet chat-first feel, but validate that desktop first action is obvious within 2 seconds.
- Quick actions stay close enough to composer and do not force a large cursor journey.

### P2-4: Legacy/parallel UI inventory should be cleaned after merge blockers

CSS still contains older sidebar sections, and TSX components like `MessageBubble.tsx`/`ThinkingIndicator.tsx` appear parallel to the current JSX chat path. Build passes because they are not on the current import path, but the component model is harder to reason about.

Acceptance:

- Mark current chat stack as canonical: `ChatWorkspace`, `MessageList`, `ChatComposer`, `WelcomeState`, `QuickActions`.
- Either wire or archive parallel TSX message components.
- Keep shared constants out of component files if Fast Refresh matters.

## Surface Acceptance Before Merge

### `/`

- Fresh load at desktop and mobile starts at top hero, not workflow.
- First viewport includes brand, H1, lead, primary CTA, and product preview hint.
- `Открыть приложение` and `Начать в Kolibri` navigate to `/app` and focus composer.
- `Тарифы` opens Control on billing section without page jump.
- No horizontal overflow at 360/390/430/768/1440 widths.

### `/app`

- Direct open and refresh of `/app` show app shell, not landing.
- Unknown paths are intentionally handled: redirect to `/app`, show app shell, or show 404 by design.
- Composer is fixed/sticky above safe-area, fully visible with mobile keyboard.
- Empty state quick actions do not overflow and keep touch targets >= 44px.
- Sending with unavailable backend shows recoverable error copy.

### Composer

- Enter sends, Shift+Enter inserts newline.
- Textarea grows to max height and resets after send.
- Disabled/loading state has a visible status and eventual retry/cancel path.
- Placeholder and typed long words do not create horizontal scroll.

### Control FAB

- Fully visible on `/` and `/app`, desktop and mobile.
- Does not overlap composer or mobile browser safe-area.
- Has stable accessible name for open/close state.
- Focus is restored here after closing Control.

### Control Panel

- Opens as dialog/sheet with focus management.
- Tabs/sections are accessible and keyboard-friendly.
- Body scroll is contained inside panel; page behind does not scroll unexpectedly.
- Billing/docs/search/cluster/settings each have loading, empty, error, and success states.

### Русские тексты

- One glossary for brand and system terms.
- No typos in visible labels or aria labels.
- Loading/error/payment copy is specific, calm, and action-oriented.
- Mixed English is intentional and limited to product/technical terms.

## Recommended Merge Gate

Do not merge until P0-1 and P0-2 are fixed and verified with screenshots or automated viewport assertions. P1 items can merge only if tracked as explicit follow-up issues with owners, except Control dialog focus if this release is intended for mobile/PWA users. P2 items are polish and maintainability, but should be batched before broad product QA.

Minimum command gate:

```bash
cd frontend
npm run build
npm run lint
npm run test:mobile-layout
```

Minimum visual gate:

```text
/ at 390x844 and 1440x1000
/app at 390x844 and 1440x1000
/app with Control open at 390x844 and 1440x1000
```

For each viewport, assert no horizontal clipping, composer visible, FAB visible, and the intended first-focus element is reachable by keyboard.
