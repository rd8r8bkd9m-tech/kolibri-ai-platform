# Local core gates — 2026-07-30 13:26 MSK

Candidate state: dirty development tree on `codex/v3-home-deploy`.

This is integration evidence for the durable runtime and authentication
changes. It is not immutable-RC evidence.

## Product backend

- Complete suite after migration 039 and bearer AG-UI integration:
  `230 passed in 42.37s`.
- Focused browser/native Product Chat auth matrix: `10 passed`.
- Focused execution adapter, cancellation, Product Chat auth and mobile auth:
  `11 passed`.
- Migration 038 → 039, queued restart recovery, expired-lease fail-closed,
  cancellation fencing, Home reclaim and warm-runtime lifecycle regressions
  pass.
- `compileall`: passed.
- Ruff `0.15.18` over the changed auth/runtime production and regression files:
  passed.
- `git diff --check`: passed.

## Web

- `npm test`: 99 passed.
- `npm run typecheck`: passed.
- `npm run build`: passed.
- The production route manifest contains
  `/api/v3/chat/runs/[runId]/events`.

## Auth and durable stream boundary

- Browser mutations retain cookie + same-origin + CSRF.
- Native mutations require a valid bearer and never fall back to a browser
  cookie when an `Authorization` header is present.
- Send, resume and cancel are bound to the exact tenant, requesting user and
  durable run.
- `Last-Event-ID` rejects malformed, negative, oversized and ahead-of-ledger
  cursors.
- Refresh rotation invalidates the previous access token; refresh-token replay
  revokes the complete device family.
- BFF and CORS forward/allow only the explicit bearer and resume headers.

## Release lane

- Portable release contract tests: 12 passed.
- Worker deployment tests: 18 passed.
- Migration-selection tests: 18 passed.
- Contract runtime tests: 4 passed.
- A temporary clean standalone archive completed migrations 001–039, web
  tests/typecheck/production build, health smoke, secret scan and
  legacy/mutable-path scans.
- The temporary archive is not a release candidate because the source tree is
  still uncommitted and the production dependency audit follow-up is active.
