---
name: kolibri-v3-development
description: Guardrails and workflows for changing Kolibri V3 (kolibri-v3/): web/PWA, native mobile, chat runtime, model providers, billing, and dev-stack operations. Use whenever working on the Kolibri V3 product, fixing UI/chat/auth regressions, integrating models or payments, or running/verifying the local dev stack. Encodes hard-won fixes so known regressions (server restarts, broken mobile scroll/auth, selectable-but-unrunnable models, stale bundles, flaky E2E) are not repeated.
---

# Kolibri V3 Development

Work inside `kolibri-v3/` only. Read `kolibri-v3/AGENTS.md` and
`kolibri-v3/docs/DEVELOPMENT_PLAN.md` before changing anything. Never touch
legacy contours (`backend/`, `frontend/`, `kolibri-v2/`, `kolibri-backend/`,
`apps/`, `ops/`, `sites/`, `kolibri-v3-new/`) for V3 work.

## Non-negotiable rules (learned from real regressions)

1. **Verify against the live stack, never typecheck-only.** The user's browser
   may receive a stale bundle (Metro/Turbopack rebuild lag, browser cache, lazy
   chunks). After a UI change, load the page in Playwright and confirm the new
   behavior AND that the served bundle contains your code. Cyrillic strings are
   often unicode-escaped in bundles; match ASCII markers or use behavior checks.
   Placeholders are attributes, not `textContent`.
2. **Never start a second dev stack.** `npm run dev` refuses to run while a
   stack is alive (pid guard in `scripts/dev-stack.mjs`). Use
   `npm run dev:persistent:restart` for restarts. Do not run heavy builds
   (`expo export`) while the stack is live. If `dev:persistent:status` reports
   `screen_session=orphaned`, the hardened script recovers it — do not manually
   kill processes; do not start a duplicate.
3. **Tailwind arbitrary-variable utilities are not emitted in this project.**
   `bg-(--composer-bg)`, `rounded-(--composer-radius)`, `p-(--composer-padding)`
   generate nothing. Style such surfaces with explicit CSS in
   `app/globals.css` at TOP LEVEL (outside `@media` blocks) or with standard
   utilities. A variable reference to an undefined token (`var(--mobile-composer)`
   in the desktop theme) makes the property invalid and renders transparent.
4. **react-native-web `pointerEvents: "box-none"` is broken** (0.21.x renders
   invalid CSS, computed style falls back to `auto`). A full-screen absolute
   wrapper with `box-none` swallows every wheel/touch event. On web use
   `pointerEvents: "none"` on the wrapper; interactive children keep `auto`.
5. **RN-web `FlatList.scrollToEnd` has stale cell metrics** and the list resets
   `scrollTop` to 0 on re-render. For chat auto-scroll, scroll the host node
   directly: `getScrollableNode().scrollTop = node.scrollHeight` inside a double
   `requestAnimationFrame`, gated by an at-bottom check; wheel/touch scrolling is
   native once no overlay blocks it.
6. **Mobile web API must be same-origin through the gateway.** The mobile PWA is
   served at the gateway (`3103`) which proxies `/v1` and `/api` to the backend.
   Never bake `http://127.0.0.1:8002` into the mobile client — on a phone that
   address is the phone itself and auth breaks. `mobile-session.tsx` already
   resolves same-origin when the gateway cookie (`kolibri_ui_client`) is present.
7. **A catalog entry is not execution.** Platform/user models
   (`platform:`/`user:` ids) are selectable and listed by the catalog, but they
   only work if the direct runtime actually executes them (see
   `_custom_model_credentials` + `_custom_model_response`). Any new selectable
   model type needs an execution path plus tests, not just a catalog row. The
   admin "connected" test only checks `GET /models`, not the chat path.
8. **E2E must isolate state.** Use a fresh user per test (register via API in
   `beforeEach`), never share the QA session across tests (rate limits and
   in-flight runs make suites flaky). Use `data-slot`/exact locators (a thread
   can be named "Новая задача"). Keep model-dependent assertions tolerant:
   providers can 429, be in arrears, or lack a key.
9. **Secrets and keys.** Never fabricate or guess API keys. The V3 backend reads
   only `kolibri-v3/.env.local` (dev-backend exports `DEEPSEEK_API_KEY` etc.).
   Check that file, the root `.env`, and the DB (`platform_models`,
   `provider_connections`) before concluding a key is missing. Turn missing-key
   errors into actionable messages. A key inside a commented line
   (`# DEEPSEEK_API_KEY=...`) is not loaded.
10. **Diagnose the right element.** When debugging scroll/hit issues, pick the
    innermost visible element (filter by on-screen rect, ancestor chain),
    verify with `elementFromPoint`, and check which layer actually receives
    events. Off-screen drawer content is still in the DOM and in the
    accessibility tree.

## Standard workflow

1. Read `AGENTS.md`, then `docs/DEVELOPMENT_PLAN.md`; append to its journal.
2. Check the stack: `npm run dev:persistent:status` (expect `running/ready`).
   Check endpoints: gateway `3103`, backend `8002`, expo `[::1]:4104`.
3. Make the change. For UI: run `npm run typecheck` / `npm run mobile:typecheck`.
   For backend: `backend/venv/bin/python -m compileall -q backend/app`.
4. Verify against the live stack (see below), then run
   `npm run verify` (quick) and the affected test suites.
5. Restart only through `npm run dev:persistent:restart`; confirm ready and all
   endpoints 200; update the plan journal.

## Live verification checklist

- Use `scripts/check-live-stack.mjs` to assert health, single-stack, and that a
  served bundle contains a marker.
- For chat/model changes, drive the real API with a fresh registered user:
  register → (select model via `/v1/profile/model-settings`) → POST
  `/v1/chat/ag-ui` → expect `RUN_STARTED` → text deltas → `RUN_FINISHED`
  (not `RUN_ERROR`).
- For mobile auth, register and log in through the gateway origin
  (`http://127.0.0.1:3103`) and confirm requests hit `/v1/mobile/auth/*` on the
  same origin.
- For composer/UI, assert behavior (send hidden when empty, slash/mention
  popovers, directive chips) in Playwright with a fresh user.

## References

- [server-stack.md](references/server-stack.md) — stack lifecycle, ports,
  restart discipline, gateway routing, orphan recovery, legacy `:3000`.
- [web-mobile-ui.md](references/web-mobile-ui.md) — Tailwind variable utilities,
  RN-web pointer events, scroll fixes, GPT-style composer, drawer pitfalls.
- [chat-models.md](references/chat-models.md) — chat execution, platform/user
  model execution, DeepSeek/provider keys, billing recurring.
- [qa-e2e.md](references/qa-e2e.md) — Playwright patterns: fresh-user isolation,
  locators, tolerant model assertions, composer spec.
