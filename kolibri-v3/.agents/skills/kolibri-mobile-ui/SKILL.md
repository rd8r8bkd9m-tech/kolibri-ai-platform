---
name: kolibri-mobile-ui
description: "Pixel-level mobile UI for the Kolibri Expo client (kolibri-v3/apps/kolibri-mobile): theme tokens, React Native Web quirks, the Liquid Glass material, and geometry driven by docs/design-evidence/mobile-chatgpt references. Use when styling or pixel-tuning mobile screens (composer, header, drawer, projects/library), implementing light/dark themes, or reproducing a ChatGPT-style layout 1:1."
---

# Kolibri Mobile UI

Work inside `kolibri-v3/apps/kolibri-mobile` only. Read `kolibri-v3/AGENTS.md`
before changing anything.

## Tokens, never literals

- `constants/theme.ts` owns `Colors` (light/dark palettes), `Radius`, and
  `Layout` (`headerControl: 40`, `composerInset: 18`, `threadMaxWidth: 768`,
  `edgeInset: 16`, `drawerFraction: 0.74`). Extend tokens there instead of
  hardcoding colors or sizes in components.
- `useTheme()` returns `{ colors, isDark, preference, setPreference }`.
  `isDark` is top-level on the hook result, NOT `colors.isDark` — the palette
  has no such field.
- Apply the theme synchronously before hydration on web
  (`readStoredPreferenceSync` in `hooks/theme-provider.tsx`) to avoid a color
  flash.

## React Native Web traps (RN 0.86 / rn-web 0.21)

- `AccessibilityInfo.isReduceTransparencyEnabled()` does not exist on web and
  throws. On web read
  `window.matchMedia("(prefers-reduced-transparency: reduce)")`; keep the
  AccessibilityInfo API for iOS/Android only.
- `pointerEvents` must live in `style` (`{ pointerEvents: "none" }`), not as a
  component prop — the prop form is deprecated and warns.
- `backdropFilter` / `WebkitBackdropFilter` / `boxShadow` strings only apply on
  web. Native uses solid colors plus `shadowColor`/`shadowOffset`/
  `shadowOpacity`/`shadowRadius` (iOS).
- A full-screen absolute wrapper with `pointerEvents: "box-none"` swallows all
  wheel/touch events on web; use `"none"` on the wrapper and let interactive
  children keep `"auto"`.
- Cyrillic strings are unicode-escaped in Metro bundles; match ASCII markers
  when verifying the served bundle.

## Liquid Glass (.regular) recipe

Compose the material from three layers, per Apple HIG:

1. **Illumination** — translucent fill: light
   `rgba(255,255,255,0.58)`, dark `rgba(40,40,44,0.62)`, plus
   `backdropFilter: "blur(28px) saturate(180%)"` on web.
2. **Highlight** — 1px inset top edge line (`inset 0 1px 0`) + a sheen
   gradient that fades within ~28px of the top edge.
3. **Shadow** — adaptive outer shadows (`0 2px 10px` + `0 12px 36px -10px`),
   deeper on focus; keep the inset highlight in the focused shadow so the
   material does not disappear.

Fall back to the solid `colors.composer` when Reduce Transparency is enabled
or the runtime lacks backdrop-filter. Avoid glass on glass. Give round
controls press feedback (`transform: scale(0.92)` + opacity), like Apple's
`.interactive()`.

## Composer geometry (ChatGPT-style, single row)

- Capsule — «в один этаж»: одна строка
  `+ → input(flex) → модель → mic → send/stop/voice`.
  `borderRadius: 27` (Radius.composer), horizontal padding `5`, page inset
  `Layout.composerInset` (18).
- Collapsed высота ~48: контролы 30px + `paddingTop 9 + paddingBottom 9`;
  input `minHeight: 30`, растёт до `maxHeight: 96` (4 строки); капсула
  растёт вверх, send/stop морфятся на месте без relayout.
- Reference screenshots live in
  `kolibri-v3/docs/design-evidence/mobile-chatgpt/`; verify geometry with the
  macOS Vision OCR script from `kolibri-mobile-qa` (02: placeholder Y≈86.3%,
  action row Y≈90.6% — референс двухуровневый, продуктовое решение — один
  ряд).

## Accessibility

- Header controls are 40px with `hitSlop` to reach 44px targets; labels and
  hints in Russian (`accessibilityLabel`/`accessibilityHint`/`Role`).
- Outline icons by default; only live/send/stop are filled.
- Respect Reduce Motion for parallax/shimmer and Reduce Transparency for
  glass.
