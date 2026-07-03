# Adaptive Directions QA

Date: 2026-07-03

## Implementation

`remote/kolibriai-frontend/src/pages/Home.tsx` now computes an adaptive direction from loaded workspace state:

- Loading: checking workspace.
- Recent estimates: continue latest estimate.
- Recent documents: return to latest document.
- Active agents: check agent tasks.
- Empty state: start with chat.

## QA

With a mocked recent estimate, the home page renders:

- `РАБОЧЕЕ ПРОДОЛЖЕНИЕ`
- `Продолжите последнюю смету`
- Pilot estimate title and total.
- `Открыть сметы` action.

Clicking the action opens the estimates route and renders the pilot estimate list.

## Evidence

- `remote/kolibriai-frontend/evidence/living-interface-2026-07-03/desktop-home-adaptive-directions.png`
- `remote/kolibriai-frontend/evidence/living-interface-2026-07-03/mobile-home-adaptive-directions.png`
- `remote/kolibriai-frontend/evidence/living-interface-2026-07-03/mobile-estimates-list.png`
