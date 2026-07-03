# Bird Animation Plan

Date: 2026-07-03

## Current State

Existing components:

- `remote/kolibriai-frontend/src/components/MascotAnimation.tsx`
- `remote/kolibriai-frontend/src/components/StatusBird.tsx`
- `remote/kolibriai-frontend/public/mascot/kolibri-cartoon.json`
- `remote/kolibriai-frontend/public/kolibri-bird.png`

Observed usage:

- Home: idle/ready mascot near the primary prompt.
- Layout: compact mascot in mobile and desktop navigation.
- Chat: mascot avatars and status bird for loading/thinking/error/success.

## Plan

- Keep the current mascot as the stable first-viewport brand signal.
- Use `StatusBird` for transient system state: idle, ready, thinking, success, warning, error.
- Keep animations lightweight and non-blocking; never hide controls while animation runs.
- Preserve reduced-motion compatibility by ensuring functional state is conveyed by text and color, not animation alone.
- Future enhancement: map backend stream states to bird states (`thinking` while request is pending, `success` after action payload, `error` after failed request).

## QA Evidence

- `remote/kolibriai-frontend/evidence/living-interface-2026-07-03/mobile-home-adaptive-directions.png`
- `remote/kolibriai-frontend/evidence/living-interface-2026-07-03/mobile-chat-response.png`
