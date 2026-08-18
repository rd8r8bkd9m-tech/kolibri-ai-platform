---
name: kolibri-mobile-qa
description: "Verifying the Kolibri mobile PWA in the browser: dev gateway routing, stale-bundle detection, Playwright, macOS Vision OCR pixel checks against design references, console-error triage, and regression tests. Use when a mobile UI change needs visual or runtime verification, or when the mobile app crashes or behaves wrong on web."
---

# Kolibri Mobile QA

Run checks from `kolibri-v3/`; read `kolibri-v3/AGENTS.md` first.

## Dev gateway

`scripts/dev-ui-gateway.mjs` (port 3103) routes by cookie
`kolibri_ui_client=mobile` to the Metro/Expo upstream (port 4104 or its socket)
and everything else to Next (3104); `/v1/*` goes to the backend (8002). The
mobile page is `http://127.0.0.1:3103/app?client=mobile`.

## Stale bundles

Metro rebuild lags and browsers cache. After editing, fetch the served bundle
with the mobile cookie and grep for an ASCII marker of the change:

```bash
curl -s -c /tmp/kb-cookies.txt "http://127.0.0.1:3103/app?client=mobile" -o /dev/null
curl -s -b /tmp/kb-cookies.txt \
  "http://127.0.0.1:3103/node_modules/expo-router/entry.bundle?platform=web&dev=true&hot=false&lazy=true&transform.routerRoot=app&transform.reactCompiler=true" \
  -o /tmp/kb.js
rg -o "ASCII_MARKER" /tmp/kb.js
```

Cyrillic is unicode-escaped in bundles — match ASCII markers. Tell the user to
hard-reload (Cmd+Shift+R) after major edits.

## Console-error triage

Known RN-web traps in this codebase:
- `AccessibilityInfo.isReduceTransparencyEnabled` is undefined on web — guard
  with `Platform.OS === "web"` and use matchMedia.
- `props.pointerEvents is deprecated` — move the value into `style`.
- `useEffect is not defined` — missing import, check the component.
- A Playwright session without login redirects to the desktop login; visual
  pixel checks then need the user's logged-in browser or an OS screenshot.

## OCR pixel checks

Compare against `kolibri-v3/docs/design-evidence/mobile-chatgpt/` with a
macOS Vision script (runs `VNRecognizeTextRequest`, prints
`X% Y% W% H% conf | text`). Reference anchors: composer placeholder Y≈86.3%,
action row Y≈90.6% (02); sidebar rows (11); projects/library search
Y≈92.6–92.7% (12/13). The 318x701 reference shows a two-level composer
(placeholder Y≈86.3%, action row Y≈90.6%); the product decision is a
single-row capsule («в один этаж») — verify the row geometry via OCR.

## Automated checks

```bash
cd kolibri-v3/apps/kolibri-mobile
npm run typecheck
npm run lint
npm test          # static source tests (28 expected)
```

Playwright console must contain no `Uncaught` errors and no deprecation
warnings. For performance, run release builds on real devices: keyboard
behavior, SecureStore, background/foreground, FPS during streaming.
