# Kolibri V3 design QA register

final result: blocked (mobile post-fix comparison evidence still open; desktop redesign items below passed local gates)

## Desktop redesign implementation QA — 2026-08-16

Result: **local candidate passed** (typecheck, 207 node contract tests, quick verify pipeline).

Implemented per `docs/design/desktop-mobile-redesign-spec.md`:

- Spec §5 sizes: navigation 320/280–360, auxiliary 400/320–640, chat hard
  minimum 640 (was 374/288–410 and 480/320–600).
- Adaptive dock/overlay: new `use-adaptive-workspace-layout` hook. Below
  920 px (or 1240 px with auxiliary docked) navigation renders as a modal
  overlay with backdrop; below 960 px the auxiliary canvas is forced
  fullscreen. The chat never shrinks below 640 px.
- The static «Инструменты» launcher page is removed (`CanvasTabContent`
  no longer has a `launcher` kind). The context toggle opens the last
  useful right-canvas surface and falls back to Files.
- Canvas header chrome is capped at three actions (fullscreen, minimize,
  close); the project picker now lives only in the workspace header.
- Escape chain: fullscreen → docked → closed, then overlay navigation
  closes. Inputs and editable regions never trigger it.
- 200% zoom redirect fixed: `MobileEnvironment` hands off only for real
  mobile platforms (iOS/Android UA or iPadOS detection). Desktop browsers
  with narrow viewports stay in the responsive Next workspace.
- Empty Files state shows «Документов пока нет» with a «Создать в чате»
  action (spec §7).
- Workspace header: decorative folder icon and sidebar-notification dot
  removed.
- Pet: initial position clamps before first paint.

Evidence: `output/design-qa/workspace/` — authenticated QA-tenant captures
at 1440×900 (docked nav), 1280×720 (spec baseline), 900×700 (overlay nav,
chat ≥640), and 1440×900 with the right canvas opening Files directly.
Capture script: `scripts/design-qa-workspace-capture.mjs` (registers and
archives a disposable QA tenant around each run).

Contract tests updated to the new spec: `tests/desktop-context-sidebar.test.mjs`,
`tests/design-contract.test.mjs`, `tests/workspace-real-data-boundary.test.mjs`
(all 207 pass).

Landing polish against the samreshuuu.ru analog: hero announce badge +
lead paragraph, featured pricing card (glow border, gradient price, pinned
CTAs), compact stats band with gradient numerals, accent case cards, FAQ
hover/open accents. Mobile 390×844 landing verified without horizontal
overflow. Evidence: `output/design-qa/landing-mobile-390.png` and
`output/design-qa/kolibri-landing-full.png`.

Open (mobile): post-fix authenticated comparison captures for settings,
projects, library, model menu and estimate editor remain open. The Expo web
dev bundle does not render in headless Chromium in this environment
(blank page, no console errors; gateway and Expo dev server respond 200),
so mobile evidence needs a manual Safari capture or a CI device run.

## Mobile ChatGPT-parity QA

### Source visual truth

- Primary dark empty-chat reference:
  `/tmp/codex-remote-attachments/019faf2c-b17d-7290-8ca8-c6d0a67d1f2e/19FD648A-2AE4-4A8F-9B9F-FD8A566C6524/1-Вставленное-изображение-1.jpg`.
- Additional user references:
  `/tmp/codex-remote-attachments/019faf2c-b17d-7290-8ca8-c6d0a67d1f2e/44FF0CAB-0C4F-446B-A05E-BCD32C431F6C/`,
  `/tmp/codex-remote-attachments/019faf2c-b17d-7290-8ca8-c6d0a67d1f2e/C028C7BC-11BB-4FEE-B5CE-83F4C67B7128/`,
  `/tmp/codex-remote-attachments/019faf2c-b17d-7290-8ca8-c6d0a67d1f2e/AF924D2B-B4E3-4C6A-98E4-F03CF14D7AA0/`, and
  `/tmp/codex-remote-attachments/019faf2c-b17d-7290-8ca8-c6d0a67d1f2e/79345E22-4696-4F47-A856-C8728FFD4FAF/`.
- Current native ChatGPT observations and uncropped captures:
  `docs/design-evidence/mobile-chatgpt/`.
- Every user reference is 590 × 1280 px. Every current iPhone Mirroring
  capture is 318 × 701 px.

### Implementation evidence

- Baseline empty chat, dark:
  `/tmp/kolibri-v3-mobile-qa-20260730/chat-dark-390x844.png`.
- Baseline empty chat, light:
  `/tmp/kolibri-v3-mobile-qa-20260730/chat-light-390x844.png`.
- Baseline narrow chat:
  `/tmp/kolibri-v3-mobile-qa-20260730/chat-dark-375x667.png`.
- Baseline estimate editor:
  `/tmp/kolibri-v3-mobile-qa-20260730/estimate-light-320x568.png`.
- Desktop regression baseline:
  `/tmp/kolibri-v3-mobile-qa-20260730/desktop-light-1440x900.png`.
- Full-view combined comparison:
  `docs/design-evidence/mobile-comparison/empty-chat-dark-reference-vs-baseline.jpg`.
- Focused comparisons:
  `docs/design-evidence/mobile-comparison/empty-chat-dark-header-focus.jpg`
  and
  `docs/design-evidence/mobile-comparison/empty-chat-dark-composer-focus.jpg`.
- Separate local Safari evidence:
  `docs/design-evidence/kolibri-safari-acceptance/`.
- Current-build mobile long-press evidence:
  `docs/design-evidence/mobile-comparison/thread-long-press-menu-390x844.png`.

The empty-chat implementation baselines are browser screenshots from before
the final drawer corrections. The current long-press state was recaptured after
the event fix with a real browser touch sequence at 390 × 844. The remaining
settings, projects, library, model-menu and estimate states still require
post-fix same-state comparison.

### Viewport and density normalization

- Source: 590 × 1280 px JPEG.
- Implementation baseline: 390 × 844 px screenshot at CSS viewport
  390 × 844 and `deviceScaleFactor: 1`.
- For the combined comparison the source was auto-oriented and normalized to
  exactly 390 × 844. The implementation remained at its native 390 × 844.
  The combined artifact is 780 × 844.
- The 318 × 701 native ChatGPT captures were intentionally left uncropped and
  unscaled because they document current behavior rather than serve as a
  pixel-for-pixel browser comparison.

### State and comparison evidence

- The valid full-view comparison covers dark empty chat.
- The focused header comparison covers hamburger size, title alignment,
  trailing action geometry and safe-area treatment.
- The focused lower-region comparison covers starter actions, icon rhythm,
  composer geometry and trailing controls.
- User references cover projects, sidebar, library, remote workspace,
  account/settings, model/effort menu, attachment menu, keyboard and active
  composer states. Those states are indexed in
  `docs/design-evidence/mobile-chatgpt/state-matrix.md`.

The empty-chat baseline preserves the intended black canvas, circular
hamburger, centered underlined `Chat` title, three starter actions and bottom
composer hierarchy. The reference includes native iPhone status/call chrome;
the browser implementation correctly does not rasterize or duplicate those
system surfaces.

### Findings

- [P1] Several final mobile interaction states still lack post-fix browser
  comparison evidence.
  - Location: settings sheet, projects, library, model menu and estimate
    editor.
  - Evidence: the long-press drawer/menu endpoint now has a current 390 × 844
    capture; the other source states do not yet have revised same-state dark
    and light comparisons.
  - Impact: geometry, transition endpoints, typography and icon alignment in
    those states cannot honestly be marked pixel-matched.
  - Fix: capture each state in the chosen browser at 390 × 844, combine it
    beside the matching source, inspect focused header/menu/composer regions,
    and repeat after any visible P1/P2 correction.
- [P1] Empty-composer live voice is not implemented.
  - Location: compact assistant-ui composer trailing controls.
  - Evidence: the source has a blue live-voice control beside the microphone;
    the implementation baseline has an honest disabled send control when the
    composer is empty.
  - Impact: a visible and explicitly requested primary interaction is absent.
  - Fix: implement a real voice session state and audio transport, including
    permission, connecting, listening, speaking, cancel and failure states.
    Do not substitute a non-functional blue icon.
- [P2] Fresh authenticated Safari response timing is not available.
  - Location: `http://127.0.0.1:3103/app`.
  - Evidence: Safari loaded the compact shell but exposed an unauthenticated,
    disabled composer. The warm reload reached that visible state in 1818 ms.
  - Impact: submit → run start → first visible answer → finish cannot be
    measured from the UI without entering an account flow.
  - Fix: repeat the bounded weather query in an already authenticated local
    Safari session. Do not alter account or security settings for QA.

### Required fidelity surfaces

- Fonts and typography: the combined empty-chat comparison shows the intended
  compact hierarchy and truncation, but focused post-fix menu/settings captures
  remain required before passing.
- Spacing and layout rhythm: the 48 px hamburger contract, compact drawer
  radius, safe-area sheet, two-column mobile file grid and 320 px estimate
  layout are code- and test-verified. Revised visual evidence remains missing.
- Colors and tokens: black/white mobile surfaces and light/dark semantic tokens
  are present in the baseline and CSS contract. Menu elevation and pressed
  colors still need same-state visual comparison.
- Image quality and assets: the empty-chat target has no decorative image
  asset. Current ChatGPT weather and generated-image captures are behavioral
  research only and are not used as Kolibri implementation artwork.
- Copy and content: the three mobile starter labels match the supplied
  reference. Existing Kolibri sidebar/settings labels and information
  architecture are intentionally preserved.
- Icons: Lucide outline icons are used consistently. Exact current-build
  sidebar, menu and voice-state comparison remains open.
- Accessibility: controls keep semantic buttons and labels; the hamburger has
  a 48 px target; thread long press preserves vertical pan, suppresses the iOS
  text callout, gives visible feedback and does not consume draft-thread taps.

### Interaction and console checks

- Native ChatGPT research exercised exact weather and image-generation prompts,
  including composed, streaming/stop, skeleton, preview and final states.
- Thread navigation regression tests prove:
  normal tap closes the drawer, a consumed 520 ms long press keeps it open for
  the action menu, draft threads do not consume long press, and mouse presses
  do not enter the touch state.
- A Chromium mobile context emitted native CDP touch-start and touch-end events
  650 ms apart. At 250 ms the pressed-row state was active; after release the
  drawer remained visible and the menu exposed `Закрепить`, `Архивировать` and
  `Удалить диалог`. A 22 px touch move cancelled the gesture, while a short tap
  opened the chat and closed the drawer without opening the menu.
- Local Safari warm reload was exercised without entering account or security
  flows. The question submission was blocked by the existing authentication
  gate.
- Browser console errors were not available because the configured Browser and
  Chrome control endpoints were unavailable. This is a final-pass blocker, not
  an inferred clean console.

### Comparison history

1. Baseline review found that the empty-chat structure was close to the source,
   while live voice and unrecorded menu/drawer states remained open.
2. Source fixes then removed desktop hover previews from the mobile overlay,
   added safe-area account treatment and directional drawers, preserved the
   primary workspace for back navigation, added a compact long-press menu, and
   replaced brittle structural CSS selectors with semantic slots.
3. Event review found that a long-press synthetic click could close the drawer
   before the child suppressed it and that draft threads could consume an
   invisible action-menu gesture. The fix adds an explicit consumed-long-press
   marker and a tested close decision; draft long press is disabled.
4. Post-fix typecheck, targeted tests, full tests and production build pass.
5. A real browser touch replay exposed a second ordering bug: Radix requested a
   menu close on touch-end before the synthetic click was consumed. The
   controlled menu now ignores only that pending close request, consumes the
   click, and remains open. The verified endpoint is preserved in
   `thread-long-press-menu-390x844.png`.

### Intentional differences

- Kolibri keeps its existing sidebar/settings destinations and product labels;
  the mobile layer changes presentation and interaction, not information
  architecture.
- Browser clients use real safe-area and visual-viewport primitives. They do
  not draw an iPhone status bar, call indicator, software keyboard or device
  frame inside the web application.
- Unsupported voice behavior remains visibly unavailable rather than being
  represented by a fake working control.

## Weather widget QA (passed)

### Scope

- Reference: `codex-clipboard-a13982bd-cee6-4e98-874f-19e4bc6542f1.png`
- Implementation: canonical assistant-ui `makeAssistantToolUI` for `get_weather`
- Desktop QA viewport: 1440 × 900
- Reference card crop: 846 × 636
- Implementation card: 736 × 542
- Side-by-side evidence: `.design-qa/weather-widget-comparison.png`

### Visual comparison

- Dark photographic rain background, large temperature, city heading, high/low
  values, five-column forecast, rounded card and inset forecast panel match the
  reference hierarchy and proportions.
- Russian labels are an intentional product localization.
- Current condition, feels-like temperature, humidity, wind, precipitation,
  observation time and source remain visible because they are useful real data,
  not demo decoration.
- The implementation uses a real raster asset and Lucide weather icons. It does
  not use CSS-drawn imagery, gradients or blur effects.

### Responsive and interaction checks

- Desktop: all five forecast days are visible without clipping.
- Narrow viewport: the main conditions remain readable and the forecast strip
  is horizontally scrollable instead of shrinking labels or overlapping.
- The widget is rendered from the real `get_weather` tool result.
- Loading state is announced with `role="status"` and the final card has a
  location-specific accessible region label.

### Dynamic scene checks

- `weatherCode` and `isDay` from `get_weather` select the scene. Text parsing is
  used only as a fail-safe for older persisted widget payloads.
- Rain: the real rain texture runs `kolibri-weather-rain-flow`; two browser
  measurements returned different transform matrices.
- Clear day: the clear-day photographic scene contains a rotating Lucide sun.
- Clear night: the clear-night photographic scene contains a floating Lucide
  moon; no sun layer is mounted.
- Cloud, snow and storm codes have dedicated scenes. Snowflakes fall and storm
  lighting pulses without changing the weather data.
- IntersectionObserver pauses every off-screen scene. Browser evidence
  confirmed `animation-play-state: paused` outside the viewport and `running`
  for the visible rain card.
- `prefers-reduced-motion: reduce` disables every scene animation.
- Narrow live-state screenshot:
  `.design-qa/weather-widget-dynamic-rain.png`.

### Intentional differences

- The reference contains English city/day labels; Kolibri uses Russian locale.
- The reference is a static design example; Kolibri keeps source attribution
  and live observation metadata.

## Desktop production acceptance QA — 2026-08-01

Result: **blocked for production; local regression candidate passed**.

- Local clean-room Playwright ran at 1363 × 936 and 1440 × 900 against a
  disposable `[QA]` tenant. All 10 tests passed, covering app load/reload,
  primary sections, settings/integrations, quick estimate action, multiple
  task switching, semantic focus, zero-result honesty, pet overlap, app-origin
  console errors and a 200% equivalent viewport. Teardown revoked sessions and
  archived the QA tenant without deleting rows.
- The pet had two defects: its initial position was rendered before the safe
  desktop clamp, and live production still lets its collapse control intercept
  the Projects button. The candidate clamps on mount and suppresses the pet
  whenever workspace/settings/dialog surfaces own interaction.
- A desktop browser crossing the responsive breakpoint at 200% zoom was sent
  to the mobile client and lost its cookie session. The candidate keeps real
  desktop browsers in the responsive Next workspace and reserves mobile
  handoff for actual mobile/touch platforms.
- Candidate screenshots are in `output/playwright/` for app, integrations,
  quick estimate and zoom states. Live screenshots are
  `output/playwright/live-1363x936-app.png` and
  `output/playwright/live-1440x900-app.png`.
- Live authenticated states were not exercised: no production QA storage state
  or safely deployed archival command was available, and creating durable test
  records without guaranteed cleanup is forbidden.
