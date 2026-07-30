# Kolibri V3 mobile interface

## Goal

Provide a mobile-first application surface that matches the approved light and
dark references without changing the established desktop workspace. The same
production assistant-ui, AG-UI, and Generative UI runtime remains responsible
for messages, streaming, tools, and Canvas content.

## Product contract

- Below 960 px the compact shell owns a dedicated mobile header and chat layout.
- At desktop widths the existing header, sidebar, resizable panels, and Canvas
  composition remain unchanged.
- The mobile start screen contains the menu, centered static `Chat` title,
  new-chat control, three assistant-ui starter actions, and a docked one-line
  composer.
- Projects, Library, navigation, model selection, account settings, and active
  chat use dedicated compact compositions backed by existing application data.
- Compact compositions preserve the existing Kolibri navigation, settings
  labels, actions, and data contracts; the reference changes their placement
  and geometry, not their product meaning.
- Model and effort selection stays inside the expanded composer instead of
  replacing the centered mobile title.
- Dark mobile mode uses a true black background. Light mode uses true white.
- Theme preference supports `system`, `light`, and `dark`, persists locally, and
  is applied before hydration to avoid a visible color flash.
- Menu, new chat, starter prompts, attachments, dictation, message submission,
  streaming, and Generative UI remain real controls rather than screenshot
  decoration.
- The iOS status bar, call indicator, software keyboard, and home indicator are
  owned by the operating system and are not recreated inside the web document.

## Responsive behavior

| Surface | Mobile | Desktop |
| --- | --- | --- |
| Navigation | Full-height left drawer with the existing Kolibri actions, real projects, and recent chats | Existing docked/preview sidebar |
| Header | Reference-driven compact header | Existing workspace header |
| Empty chat | Open canvas with three quick actions near composer | Existing Kolibri welcome and four cards |
| Composer | Collapsed capsule; focused two-row state with attachment, model/effort, input, dictation, and submit | Existing multi-row assistant-ui composer |
| Projects | Compact tabs, real project list, bottom search | Existing overview/table |
| Library | Compact filter tabs, real artifact grid, bottom search | Existing file manager |
| Account | Mobile layout of the same settings groups and appearance controls | Existing account surface |
| Canvas / Generative UI | Existing modal/primary mobile surface | Existing resizable workspace |
| Estimates | Full-width item cards with touch-sized inputs and sticky totals | Existing estimate table |

## Theme states

- System: follows `prefers-color-scheme` and reacts to operating-system changes.
- Light: fixed white mobile canvas and existing light desktop tokens.
- Dark: fixed black mobile canvas and existing dark desktop tokens.
- The choice is available from the account `Внешний вид` section.

## Acceptance checks

1. Render `/app` at 390 × 844 and at the 591 × 1280 reference size.
2. Compare dark mobile layout, spacing, typography, icon treatment, and composer
   geometry against the approved screenshot.
3. Switch dark → light → system and verify persistence after reload.
4. Open the mobile navigation drawer, create a new thread, and long-press a
   conversation to verify the existing pin/archive/delete actions.
5. Activate a starter action, type in the composer, and verify assistant-ui state.
6. Open an estimate at 320 px and verify that cards, totals, and inputs fit with
   no horizontal overflow.
7. Render a desktop viewport and confirm the established shell has not shifted.
8. Run typecheck, contract tests, and a production build with no framework error
   overlay or relevant console errors.
