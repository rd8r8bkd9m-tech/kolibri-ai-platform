# Native mobile evidence

## Scope

Evidence for the canonical Expo / React Native client in
`apps/kolibri-mobile`. This folder records only checks actually executed; web
Safari evidence belongs to the separate responsive-web workstream.

## 2026-07-30 — pet mini-assistant and construction vertical

Implemented:

- a static Metro registry for all ten reviewed Kolibri 3D-cartoon pet assets;
- a functional pet mini-assistant bound to the same active
  `@assistant-ui/react-native` composer and thread as the primary chat;
- real runtime status mapping (`running`, `complete`, `incomplete/error`,
  `cancelled`) without a second history or fabricated response;
- Reanimated motion with Reduce Motion support, native haptics, Android Back,
  keyboard-safe positioning and accessibility labels/live status;
- a compile-time construction-estimate renderer and real V3 client for document
  catalog, estimate open and optimistic-version PATCH save;
- fail-closed access when the required capability and entitlement are absent.

Source assets:

- `public/pets/manifest-v1.json`;
- `public/pets/active/*.webp` (512 × 512);
- `public/pets/thumbs/*.webp` (144 × 144);
- release copies under `apps/kolibri-mobile/assets/pets`.

Server projection:

- V3 identity now returns `construction.estimates.workspace` and
  `construction.estimates.use` only from an active, exact tenant/user grant;
- the trusted owner bootstrap receives the first construction release grant;
- every other subject stays denied until a server-side subscription/admin
  operation persists a grant; no client-controlled claim is accepted.
- migration `038_product_entitlement_projection.sql` owns the persisted grant,
  immutable subject scope and epoch-fenced revoke/regrant transition;
- browser session, mobile login, refresh and bearer session all use the same
  live server projection.
- all estimate document, editor, export, calculation, pricing, construction
  context, normative-reader and personal-price routes enforce the entitlement
  on the server; chat estimate acceptance and delayed widget materialization
  enforce it independently as well;
- the platform owner can grant or revoke the exact entitlement for an ordinary
  customer through a CSRF-protected control-plane operation with expected
  epoch, immutable target scope and an audit event.

Verification status:

- `npm run typecheck` — passed.
- `npm run lint` — passed (the existing legacy-config notice is non-blocking).
- `npm test` — 5/5 focused native vertical contract tests passed.
- `npx expo-doctor` — 20/20 checks passed.
- `npm run export:ios` — passed; Metro bundled 2,528 modules and included all
  twenty active/thumbnail pet assets.
- `npm run export:android` — passed; Metro bundled 2,602 modules and included
  all twenty active/thumbnail pet assets.
- full backend `pytest -q` — 222/222 passed after the projection and API
  authorization boundary.
- focused Ruff check for the new projection/bootstrap modules and tests —
  passed.
- No iOS Simulator, Android Emulator or physical-device result is claimed in
  this evidence entry.
- Pixel-level native design QA is blocked until the canonical ChatGPT replay
  capture is copied into this V3 evidence tree and the same app state is
  captured from a simulator/device.
