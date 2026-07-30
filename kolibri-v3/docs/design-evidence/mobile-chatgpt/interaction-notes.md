# ChatGPT mobile interaction notes

## Session and evidence boundary

- Date/time observed in the phone status bar: 11:40–12:38 on 2026-07-30.
- Mirrored capture dimensions: 318 × 701 px, JPEG, no crop or rescale after
  capture.
- Theme observed: light. The persistent theme preference was not changed.
- Input path: Mac hardware keyboard forwarded to the focused iPhone composer.
  This intentionally did not fabricate an iOS software keyboard.
- ChatGPT's internal iOS controls were not exposed in the macOS accessibility
  tree. `Tab`, `Shift+Tab`, and `Escape` did not move visible focus to header,
  plus, model, or voice controls.
- Read-only boundary: no account/privacy/security settings, permissions,
  credentials, subscription, purchase or file upload was changed.

## Empty chat geometry (`01-empty-chat-light.jpg`)

- The iOS status area occupies roughly the first 79 px, with a centered black
  Dynamic Island about 95 × 30 px.
- Header control centers are approximately `(39, 100)`, `(166, 100)`, and
  `(280, 100)`.
- The hamburger and new-chat outlines are approximately 38–40 px circular
  controls with a thin neutral stroke. Icons are outline-only.
- `Chat` is centered, semibold, underlined and paired with a small down
  chevron. It does not carry the selected model name.
- Starter rows begin near y=478 and repeat at about a 39 px baseline interval.
  Icons are quiet outline glyphs; labels carry the visual weight.
- The composer is inset 18 px from each side and occupies y=590–668. In this
  live build it is already a two-row 78 px capsule on an empty chat:
  placeholder above; plus, `5.6 Средний`, microphone and blue live-voice
  control below.

## Composer behavior (`02`, `03`, `06`)

- Focus changes the caret and input content without moving the fixed bottom
  action row.
- A one-line weather prompt keeps the composer at about 78 px.
- A four-line image prompt expands it upward to about 139 px; the bottom row
  stays aligned and the send action remains a 30 px blue circle.
- The placeholder uses medium gray; entered text uses high-contrast black with
  a compact, bold-ish mobile weight.
- Mac hardware input suppresses the software keyboard in this mirror session,
  so keyboard dimensions and animation remain unconfirmed.

## Streaming and stop (`04`, `07`)

- Pressing Return while the composer is focused submits the message.
- The first captured streaming state appeared within the approximately 0.5 s
  Computer Use action round-trip.
- The blue live/send circle changes to a blue stop circle containing a white
  square. Geometry remains fixed; no composer relayout occurs.
- Empty-chat header content changes after the first user message: the centered
  title disappears and the right action becomes an edit + overflow capsule.

## Weather result (`05-weather-result-light.jpg`)

- User messages are soft-neutral rounded bubbles aligned right.
- The weather block starts with a compact rounded temperature pill, a bold
  two-line condition and a muted location label.
- Three forecast rows use a small weather glyph at left, bold weekday,
  right-aligned high/low values and hairline separators.
- Assistant prose follows directly below the card, left aligned at the same
  20 px content inset.
- A 32 px circular scroll-to-bottom control floats centered above the composer.
- Weather query used exactly: `Какая погода в Москве?`

## Image generation (`06`–`10`)

- Prompt used exactly: `Создай изображение: реалистичная колибри над
  современным строительным чертежом, квадратный формат.`
- Initial generation state: muted `Думаю` label and a 230 × 307 rounded
  placeholder (`08`).
- Preview state: placeholder widens to almost the full 278 px content width,
  adds a top-right `Предпросмотр` pill and a four-slot thumbnail strip (`09`).
- Final state: a 278 × 278 rounded image, bottom-left `Редактировать` pill and
  bottom-right circular share control (`10`).
- A secondary share icon and overflow pill sit below the card.
- The completed capture shows `Рассуждение остановлено` even though no stop
  control was manually pressed and the image completed. Treat this as observed
  product copy, not as evidence that generation failed.

## Iconography and motion notes

- Header, starter, composer and result actions use a consistent thin outline
  icon family; filled color is reserved for the live/send/stop emphasis.
- Hit areas are materially larger than their glyphs and use circular or
  stadium-shaped outlines.
- Press/slide/long-press motion could not be measured in the current automated
  session because the mirrored iOS view did not expose internal AX controls.
  The exact missing motion states are enumerated in `state-matrix.md`.

## Sidebar and destination geometry (`11`–`16`)

- The open sidebar occupies roughly 233 px of the 318 px capture, leaving a
  narrow live strip of the previous destination visible at right.
- The sidebar uses no dimming scrim in the captured light state. Its trailing
  edge is softly rounded and elevated above the preserved destination.
- Primary destination baselines are approximately 43 px apart. Search,
  new-chat and settings controls remain reachable at the bottom.
- The projects screen keeps three header controls at centers near
  `(39, 100)`, `(159, 100)` and `(280, 100)`. Four rows and their secondary
  timestamps fit above a fixed bottom search field.
- The library grid uses two columns with roughly 12 px between them. Folder,
  generated-image and document tiles share the same rounded cell geometry
  while preserving their distinct content.
- Remote places horizontally scrollable connection chips directly below the
  header, followed by project and chat sections. Search and the blue `Чат`
  action remain fixed at the bottom.
- The remote sort sheet occupies approximately x=105–299 and y=84–484. It
  groups three sorting choices above five management choices with one divider.
- Remote connection settings open as a full-height light sheet with a rounded
  top. Connection switches and editor preferences were observed but not
  changed.
- Only fully settled endpoints were captured. The Computer Use round trip did
  not expose reliable intermediate drawer frames, so slide duration and easing
  remain unmeasured.

## Gesture control limitation

- After explicit authorization, normal coordinate clicks worked when the
  iPhone Mirroring window was freshly targeted and raised.
- The available Computer Use API exposes `click` and `drag`, but no
  pointer-down duration. A one-pixel drag intended only to test whether a hold
  could be represented failed with `noWindowsAvailable` and did not change the
  phone.
- Right-click is not recorded as an equivalent to a native iOS long press.
  Haptic timing, pressed-row scale/highlight and the current conversation menu
  endpoint remain unconfirmed.

## Back transition (`18`–`20`)

- `18-active-chat-back-light.jpg` records an active remote conversation with a
  38–40 px circular back target at approximately `(38, 100)`.
- Activating that target produced
  `19-back-transition-intermediate-light.jpg`, where the destination chat list
  is visibly translated in from the trailing side while the preceding view
  clears.
- `20-chat-list-light.jpg` is the settled endpoint with `Чаты` selected,
  `Источники` adjacent, the list independently scrollable, and the composer
  still docked at the bottom.
- The intermediate capture proves a directional transition exists. Computer
  Use capture latency prevents assigning a reliable animation duration or
  easing curve from these three frames alone.
