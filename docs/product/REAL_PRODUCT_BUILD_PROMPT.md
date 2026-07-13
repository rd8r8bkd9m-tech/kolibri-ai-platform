# Kolibri AI — build the real product, not a demo

You are implementing the first release candidate of Kolibri AI. This is a
production product task, not a concept, dashboard, collection of cards, static
mock, or documentation exercise.

## Outcome

Create one coherent product on `kolibriai.ru`:

- `/` — premium public landing page with a working first composer;
- `/app` — the real Kolibri conversation workspace;
- `/developers` and `/docs` — honest, minimal product/API entry points;
- `/control` — owner-only live factory view, never included in the public
  navigation or public data bundle;
- `/v1/*` — the existing OpenAI-compatible backend contract.

The landing composer must create or restore a public session, create a project,
carry the user's exact text into `/app`, submit it to `POST /v1/responses`, and
show the streamed answer. This path must work from an empty browser profile.

## Absolute boundaries

1. Create a new application at `apps/kolibri-product/` from scratch.
2. Do not import, copy, rename, or patch components or CSS from any existing
   Shell, Vista, kiosk, portal, dashboard, `apps/kolibri-shell*`, or legacy
   frontend directory. Existing code may be read only to understand public API
   contracts.
3. The only visual sources are:
   - `docs/design/approved/kolibri-shell-desktop.png`;
   - `docs/design/approved/kolibri-shell-mobile.png`;
   - `packages/brand/kolibri-bird.png`.
4. Render the official bird asset exactly once on a visible surface. Do not
   redraw, recolor, approximate, or duplicate it.
5. No placeholders, fake metrics, seeded factory counts, `Скоро`, dead buttons,
   fake success copy, or generic “verified response” fallback.
6. Do not expose providers, server topology, credentials, internal prompts, or
   private chain-of-thought to public users.
7. Do not deploy, modify DNS, credentials, firewall, production units, or data.

## Product behavior

### Landing `/`

- Quiet ivory/white canvas, deep ink text, restrained teal/orange accents from
  the mascot; premium typography and generous spacing.
- One concise value proposition: Kolibri turns an ordinary request into a
  checked result — answer, research, estimate, document, image, site or app.
- A real composer is the primary action above the fold. Examples may populate
  the composer but may not pretend to execute.
- Minimal navigation: Product, Developers, Security, Sign in. Do not place
  vertical capabilities in a permanent menu.
- Submitting transitions to `/app` without losing the request or duplicating it.

### Shell `/app`

- The current project conversation is the main canvas. A second message
  continues the same project and never creates a new window by itself.
- Desktop: compact top bar, one project selector, History and overflow, centered
  readable conversation, fixed composer. No permanent sidebar in the approved
  state.
- Mobile: one full-screen surface, 17–18 px body text, 44 px minimum controls,
  one vertical scroller, no horizontal overflow. History/Files/Tools are sheets;
  artifacts/editors are full-screen surfaces.
- One shared mascot/menu slot morphs between bird and menu. Both controls are
  never visible at once. Respect reduced motion.
- Work Trace streams safe factual stages, actors, tools, sources, checks and
  verdicts. It must be driven by response events, not timers or hardcoded
  completion.
- An artifact appears inline only after real metadata: id, bytes URL, MIME,
  positive size, SHA-256 and verifier binding. Detach opens one deduplicated
  workspace surface.
- The composer remains visible with mobile safe areas, `visualViewport` and the
  software keyboard. `+` lists only backend-invocable capabilities with a live
  route and implemented renderer.

### First artifact: estimate

- Display a clear name such as
  `Смета: Одноэтажный дом 100 м² — Лениногорск, Татарстан`.
- Desktop uses an editable table; mobile uses a readable summary and opens a
  full-screen editor.
- Numeric fields are `type=text` with `inputMode=decimal`; no browser spinners.
- Totals come from saved backend revision data, never hardcoded client sums.
- Status is `needs_input`, `preliminary`, `source_backed`, or `verified`.
  `verified` requires source/date/region/unit provenance.
- PDF action is visible only when real PDF bytes exist and verification passes.

## Required frontend architecture

- React + TypeScript strict + Vite.
- Small route components and feature packages; no monolithic `App.tsx`, global
  transport module, or multi-thousand-line stylesheet.
- Required boundaries: `app`, `routes`, `components`, `features/conversation`,
  `features/projects`, `features/work-trace`, `features/artifacts`,
  `features/estimates`, `api`, `state`, `styles`, `tests`.
- Central design tokens. Inter Variable for the application, Manrope Variable
  for marketing headings, with system fallbacks.
- One icon library for standard controls; no emoji, CSS art, custom inline SVG,
  or text glyph icons.
- No Service Worker in this release.

## Required API behavior

- Browser bootstrap: `POST /v1/shell/bootstrap` only. No expected 401/403 GET.
- Responses: `POST /v1/responses`, durable status, resumable SSE events and
  idempotent cancel.
- Projects/history: real repository operations, create/open/delete/restore and
  persistence across reload.
- Typed errors must preserve retry/route information. Never render raw backend
  exceptions to the user.
- Unknown `/api/*`, `/v1/*` and hashed assets return real 404 responses, never
  the SPA document.

## Required states

Every core surface must implement and test empty, loading, streaming, waiting
for input, approval, recoverable error, terminal error, completed and cancelled
states. Buttons shown in these states must perform their action.

## Acceptance tests

The work is accepted only when all of the following are true:

1. `npm test`, typecheck, lint and production build pass.
2. Architecture tests prove no imports from legacy frontend directories.
3. A fresh-browser E2E submits `привет` on `/`, lands on `/app`, creates one user
   message and one assistant stream, and keeps the same project for the next
   message.
4. History create/open/delete/cancel/confirm/undo/reload works.
5. Desktop active-estimate state visually matches the desktop source at
   `1487 × 1058` with no actionable P0/P1/P2 drift.
6. Mobile active-estimate state visually matches the mobile source at
   `393 × 850`, with visible composer and zero horizontal overflow.
7. Exactly one official mascot is visible.
8. Browser console has zero application errors; there are no bootstrap 401/403,
   ResizeObserver-null, module-MIME, service-worker or missing-asset errors.
9. A failed provider route produces an honest actionable state and tries the
   configured fallback; it never produces a fake success.
10. A real artifact test verifies bytes, MIME, size and SHA-256 before display.
11. `design-qa.md` records source path, implementation screenshots, viewports,
    comparison history and exact `final result: passed` only after comparison.
12. The branch contains a commit, is pushed, and the result reports commit SHA,
    tests, screenshots, changed files, blockers and next action.

## Execution roles

- Product Shell implementer owns only `apps/kolibri-product/**`.
- Backend implementer owns only the public session/response/project contracts
  and their tests.
- Browser verifier owns only E2E/QA evidence and may not change product code.
- Reducer merges only commits that pass their independent contracts.

If a dependency or credential is missing, return an exact blocker and keep the
product state honest. Never replace missing execution with a simulated result.
