# QA / E2E patterns

## Fresh-user isolation (non-negotiable)

Every Playwright test registers a brand-new user (via UI or API) in
`beforeEach` — never share the QA session across tests. Shared sessions hit
rate limits and in-flight runs and make suites flaky. See
`scripts/qa-mobile-chat.mjs` and `scripts/qa-mobile-flow.mjs` (both register a
fresh user through the mobile UI; `qa-mobile-chat` sends 12 long messages,
`qa-mobile-flow` does register → stream → reload → drawer → account → logout →
login).

## Locators

- Use `data-slot` / exact accessibility labels. A thread can legitimately be
  named «Новая задача», so label-based locators must be unambiguous
  (`getByLabel("Сообщение")`, `getByRole("button", { name: "Отправить подсказку" })`).
- Off-screen drawer content is still in the DOM and accessibility tree:
  `elementFromPoint` and locators resolve it while clicks fail. Filter by
  on-screen rect before concluding a control is broken (see
  `web-mobile-ui.md` → Drawer).
- Accept native browser `confirm` dialogs (`page.on("dialog", d => d.accept())`).

## Tolerant model assertions

Providers can 429, be in arrears, or lack a key. Keep model-dependent
assertions tolerant:

- Assert the wire protocol (RUN_STARTED → text deltas → RUN_FINISHED), not the
  exact final text.
- For chat/model changes, drive the real API with a fresh user: register →
  (select model via `/v1/profile/model-settings`) → POST `/v1/chat/ag-ui` →
  expect `RUN_STARTED` → deltas → `RUN_FINISHED` (not `RUN_ERROR`).

## Stale-bundle detection

A fresh Metro bundle may lag behind the source. Before exercising a changed
UI, reload until a known marker appears in the served page
(`globalThis.__KOLIBRI_MOBILE_ENTER_SEND__`; `qa-mobile-flow.mjs` retries up
to 5 reloads). Cyrillic strings are often unicode-escaped in bundles — match
ASCII markers or behavior, not visible text.

## Composer spec

- Send button hidden when the composer is empty; visible when non-empty.
- Enter submits (web); the keydown can arrive before the last `onChange`
  propagates — read the value from the DOM target and sync via
  `aui.composer.setText` before `aui.composer.send()`.

## Commands

- `npm run test:qa:mobile:chat` / `test:qa:mobile:flow` — behavioral E2E on the
  live stack (gateway 3103, viewport 390×844, iPhone UA).
- `npm run check:ui-gateway` / `check:mobile-app` — routing + shell smoke
  (require a live stack; deliberately not part of `npm run verify`).
- `npm run test:qa:estimate:live` — live estimate QA.
- Full gates: `npm run verify` / `npm run verify:full`.

## Related

- `kolibri-mobile-qa` — pixel checks via macOS Vision OCR + Pillow against
  design references.
- `kolibri-v3-development` — live verification checklist.
