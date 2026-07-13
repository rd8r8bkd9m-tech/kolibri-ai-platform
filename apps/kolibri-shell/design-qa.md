# Kolibri Shell design QA

- Source visual truth (desktop): `docs/design/approved/kolibri-shell-desktop.png`
- Source visual truth (mobile): `docs/design/approved/kolibri-shell-mobile.png`
- Implementation screenshot: `/var/folders/jq/2t_cj7ns76sbdkcc3rb0l_6h0000gn/T/com.openai.sky.CUAService/Yandex Screenshot 2026-07-12 at 8.21.36 PM.jpeg`
- Desktop viewport: 1228 × 768 browser capture at 110% Yandex zoom.
- Source state: active `Дом 100 м²` estimate conversation with completed work trace and inline estimate artifact.
- Implementation state: disconnected empty conversation.

## Full-view comparison evidence

The two approved source images and the rendered Yandex capture were opened in one comparison input on 2026-07-12. They do not represent the same visual system or product state. The implementation uses the earlier warm empty-state shell; the approved target is an active conversation whose artifact becomes the workspace.

## Findings — iteration 1

- **P1 — Wrong product composition**
  - Location: entire Shell.
  - Evidence: the desktop source is an active project conversation with inline estimate editor, action rail, PDF row and floating composer. The implementation is dominated by a centered empty-state headline and a separate connection banner.
  - Impact: the primary result-as-workspace behavior is absent and the product reads as the rejected old design.
  - Fix: make the project conversation the canvas and render the typed estimate artifact inline; move connection state into the compact work/status surface instead of creating a banner above the product.

- **P1 — Header does not match the approved morphing control**
  - Location: top bar / `MascotMenuButton` / project heading.
  - Evidence: source shows the official bird as the visible project/menu character, project title at the left on desktop and centered on mobile, plus compact History/overflow actions. Implementation shows a generic hamburger, centered `Kolibri / Новый диалог`, and a separate new-chat icon.
  - Impact: brand identity and navigation hierarchy are materially different.
  - Fix: implement the exact bird↔menu morphing slot and source-specific project/history/overflow layout without duplicating the bird.

- **P1 — Work trace and artifact workspace missing from the compared state**
  - Location: conversation result.
  - Evidence: source contains a five-step horizontal trace on desktop and compact actor/status card on mobile. Implementation contains neither in the rendered state.
  - Impact: the defining agentic behavior cannot be evaluated or used.
  - Fix: add a development-only deterministic active-estimate fixture for visual QA while keeping the production build API-driven; assert the fixture is absent from the production bundle.

- **P1 — Mobile evidence missing and desktop composition cannot collapse into the approved sheet**
  - Location: 390 × 844 mobile state.
  - Evidence: mobile source uses large chat typography, a live-work card, rounded estimate sheet and safe-area composer. No same-state mobile implementation capture exists yet.
  - Impact: mobile fidelity and persistent composer visibility are unproven.
  - Fix: implement a dedicated mobile composition, capture at 390 × 844, and compare it with the source before handoff.

- **P2 — Typography, spacing and color tokens drift**
  - Location: global tokens and Shell CSS.
  - Evidence: source is predominantly white with restrained teal and very light neutral surfaces; implementation uses warm ivory, amber warning emphasis, a large marketing headline and different vertical rhythm.
  - Impact: even if functionality is added, the UI will still look like the rejected older line.
  - Fix: derive the new white/ink/teal/neutrals, radii, type scale and spacing directly from the source images.

- **P2 — Official mascot asset is present but used in the wrong state**
  - Location: top-left control.
  - Evidence: the exact approved PNG hash is present, but it is visually hidden until hover/open while the source shows it as the persistent character.
  - Impact: correct bytes alone do not produce source fidelity.
  - Fix: keep the same asset unchanged and correct its visible scale, placement and morph behavior.

## Focused-region comparison

The header, work trace, estimate surface and composer were readable in the full-view desktop source/capture, so they were evaluated directly. A focused mobile comparison is still required after a same-state 390 × 844 capture exists.

## Implementation checklist

1. Replace the old empty-state composition and tokens.
2. Rebuild desktop active-estimate state from the approved source.
3. Rebuild mobile as a dedicated full-screen/sheet composition.
4. Preserve canonical bootstrap, idempotency, SSE and artifact verification contracts.
5. Capture desktop and mobile at matching states/viewports.
6. Repeat comparison and resolve every P0/P1/P2 issue.

## Comparison history

- Iteration 1: rejected old warm Shell captured in Yandex; six actionable P1/P2 mismatches remain. No fixes have yet been compared.

## Final result

final result: blocked
