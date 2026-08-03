# Live production acceptance — 2026-08-01

## Source and deployed release

- Local branch: `codex/v3-home-deploy`.
- Inspected local HEAD: `0874ec5a510d04ccd1ad33af319be0b47df51fbe`.
- Live `/api/health` release commit: the same exact commit.
- Published refs differ: `origin/codex/v3-home-deploy` is
  `9ae232df0f803e2db0a006efe813afec5d7304e3`; `origin/main` is
  `73f79e09e5b861501800e01444bba3be63c1a14d`.
- The live/local commit is not reachable from the inspected published refs.
- The acceptance changes are uncommitted and are not represented by the live
  release identity.

## Live observations

- `/app`: HTTP 200 at both required desktop viewports; unauthenticated shell
  and semantic navigation render; reload has zero console errors.
- Pet: at 1363 × 936 its collapse control intercepts the Projects button.
- `/api/v1/health`: HTTP 404 while `/api/health` is healthy.
- Headers disclose `nginx/1.24.0 (Ubuntu)` and `X-Kolibri-Release`; CSP and HSTS
  are absent; X-Frame-Options is `SAMEORIGIN`.
- Authenticated live acceptance was not performed without a disposable QA
  credential and production-safe archival mechanism.

## Local candidate gates

- `npm run verify:full`: passed.
  - backend: 331 passed;
  - web: 162 passed;
  - Rust estimate kernel and storage executor: fmt, clippy `-D warnings` and
    all tests passed;
  - Next production build passed;
  - mobile typecheck, 18 tests and lint passed.
- `npm run test:e2e:desktop`: 10 passed across 1363 × 936 and 1440 × 900.
- CSP enforce-mode production build and Chromium smoke passed with zero console
  errors. The compatible enforced policy retains `unsafe-inline` for Next
  bootstrap while the stricter no-inline policy remains report-only; nonce
  propagation and production rollout remain required hardening work.
- Root `npm audit --audit-level=high`: zero vulnerabilities.
- Mobile audit: high findings reduced to zero; 11 moderate transitive
  Expo/xcode/uuid findings remain because the offered fix is breaking.
- Python `pip-audit` and Rust `cargo-audit` executables are unavailable in the
  workspace, so no clean claim is made for those scanners.
- Portable backup/restore rehearsal test passed. No immutable-candidate canary
  rollback or current external monitoring proof exists.

## Decision

Production verdict: **BLOCKED** until a clean commit is published, built,
deployed with exact identity, then re-tested on a disposable production QA
tenant with CSP enforcement, canary, monitoring and rollback evidence.
