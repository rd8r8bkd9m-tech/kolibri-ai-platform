# Kolibri V3 R1 — release control board

Updated: 2026-07-30 18:59 MSK  
Target: 2026-08-06 18:00 MSK  
Production: `https://kolibriai.ru/app`  
Decision authority: product owner

This file is the operational resume point after any interruption. The
roadmap defines scope; this board records current truth. A workstream is not
`DONE` until its required test, artifact or runtime evidence is linked here.

## Status vocabulary

- `DONE` — implementation and required evidence both exist.
- `ACTIVE` — owned work is being implemented now.
- `READY` — implementation exists; a wider integration or release gate is next.
- `BLOCKED` — the named external or technical condition prevents the gate.
- `NOT STARTED` — no release-candidate implementation is being claimed.

## Current workstreams

| Priority | Workstream | Status | Owner | Evidence / next gate |
|---|---|---|---|---|
| P0 | Canonical V3 source | READY | release lead | Expo app is under `apps/kolibri-mobile`, the Rust kernel is under `packages/estimate-kernel-rs`, and the repository-wide release audit rejects committed parent-level V3 Home/Primary/bare-metal lanes. A clean authorized candidate commit remains |
| P0 | Durable chat Stop | DONE | backend/runtime | Server terminalization, Home/direct outbox fencing, direct runtime pre-emption, web and native client wiring are implemented; restart/cancel regressions and the complete backend suite pass at `280 passed` |
| P0 | Trusted A2A binding v1.3 | DONE | runtime/A2A | Exact frozen profile/workspace/epoch propagation, transactional lease claim/renew/takeover, pre-I/O and pre-commit fences, revoke/cancel and fail-closed downgrade are integrated |
| P0 | Trusted workspace leases | DONE | runtime/worker | Migration 037 and the real product worker implement issue/claim/renew/fence/terminalize/revoke; raw capability tokens remain worker-memory-only |
| P0 | Browser/native Product Chat auth | DONE | identity/chat | Cookie+CSRF and bearer send/resume/cancel, strict tenant/user isolation, refresh rotation/replay-family revocation, BFF forwarding and explicit CORS are covered; web is `128/128` and the full backend is `280 passed` |
| P0 | One Product/Data backend | READY | release lead | V3 contract runtime is self-contained; portable tests are `16/16`, the repository-wide single-lane audit passes, an isolated clean working-tree preview passed full smoke and the web dependency audit is `0`. A clean authorized candidate commit remains |
| P0 | Persistent runtime and latency | READY | runtime/release | Current schema 44 retains the migration 039 durable direct queue, startup recovery, exact leases/fences, heartbeat and one process-lifetime dispatcher. Canonical restart applies migrations and validates exact owner `montodays@ya.ru`, active policies and credential structure before port 8002. The backend default database is now rooted at the V3 source, so a wrong working directory cannot silently select `backend/var`. The previous owner credential was restored from the pre-override backup and its login throttle was cleared. A real `/api/agui` prompt returned `работает` in 7.12 s. Immutable-candidate/live-provider timing remains; see `evidence/local-owner-migration-release-identity-2026-07-30.md` |
| P0 | CI / clean RC / immutable build | ACTIVE | release lead | Local V3 workflow covers web, backend, 90 schemas, Rust and Expo; web audit is `0`, web is `128/128`, backend is `280 passed`, portable tests are `16/16`, and typecheck/build pass. A clean isolated schema-44 archive passed full production smoke using the real Product worker launcher and one exact release ID/commit across backend, worker and standalone frontend. The production renderer now supplies the same monitor/backup units to installer and Linux `systemd-analyze`; remote green, external alert delivery, final-candidate smoke and a clean authorized candidate remain. See `evidence/local-release-observability-alerts-2026-07-30.md` |
| P0 | Backup, restore and rollback | ACTIVE | release/ops | The canonical local database passed online backup, byte-exact restore, integrity/FK verification and a rolled-back real write probe. The installer uses the same packaged helper and now installs a daily verified backup timer plus a minute release monitor from one CI-verifiable renderer. Immutable-RC and canary code rollback remain; see `evidence/local-database-backup-restore-rehearsal-2026-07-30.md` and `evidence/local-release-observability-alerts-2026-07-30.md` |
| P1 | Mobile web parity | ACTIVE | mobile web | Web tests are `128/128`; real 650 ms browser touch QA proves the conversation long-press menu, cancellation by movement and ordinary tap behavior; remaining same-state comparisons and live voice are open |
| P1 | Expo / React Native | READY | native mobile | No WebView; typecheck, lint, tests `5/5`, Expo Doctor `20/20`, iOS 5.7 MB export and Android 5.9 MB export pass; no simulator/emulator/device runtime is available |
| P1 | Native construction estimate slice | READY | native vertical | Real `/v1/documents` plus versioned `GET/PATCH /v1/projects/{id}/estimate`; capability and entitlement fail closed, with no mock data; export/test evidence is next |
| P1 | Functional animated pets | READY | native/product UI | Ten real pet assets, Reanimated states, reduced motion, haptics, accessibility and same-thread `ComposerPrimitive` mini-assistant implemented; export/test evidence is next |
| P1 | Owner control plane | READY | platform admin | Owner-only storage inventory/control contracts, epoch checks, CSRF/recent-auth, status reconciliation and retained-quarantine restore are implemented and pass desktop plus 390×844 browser QA. The shipped Rust executor is independently verified fail-closed/capacity-only with debug and release tests `27/27`; mutation remains blocked until exhaustive guard evidence, Linux CI, Primary mTLS and true step-up auth |
| P1 | Construction entitlement | DONE | product authority | Server-owned deny-by-default grant/revoke projection gates browser, bearer, estimates, pricing, normative data and chat materialization; owner control and immediate revoke are covered by the current `272 passed` backend suite |
| P1 | Mobile visual research | ACTIVE | design research | Durable screenshot/state-matrix capture is now mandatory; no future claim may depend on an ephemeral video-replay session |
| P1 | Estimate/Rust conformance | READY | estimate engine | The estimate kernel remains shadow-only and production authority remains Python/server until its parity gate. The separate storage executor uses a strict Rust protocol, but its mutating path remains fail-closed pending exhaustive live guard evidence and approved transport |

## Critical path

1. Finish the canonical release-lane audit and create a clean candidate.
2. Repeat the proven estimate, weather, image and attachment journeys on that
   candidate with the approved live providers.
3. Repeat the complete backend/web/contracts/Rust/Expo gate.
4. Prove the 12-step user journey on the local production build.
5. Freeze one immutable candidate; run security, backup/restore and rollback.
6. Run physical iPhone Safari and Android Chrome acceptance.
7. Run canary, collect release evidence, and request explicit owner GO.

## Resume protocol after any stop

1. Read this file, `docs/PRODUCTION_ROADMAP_2026-08-06.md` and
   `release-plan.yaml`.
2. Inspect `git status` without deleting, resetting or overwriting user work.
3. Inspect active helper assignments and their latest evidence; do not restart
   completed work or silently abandon active work.
4. Resume the highest unfinished P0 on the critical path. A new idea enters
   the backlog unless it blocks that path.
5. Update this board whenever a gate changes state and link the exact command,
   test count, screenshot, trace or artifact.
6. Never equate “code written”, “HTTP 200” or a screenshot alone with release
   completion.

## Immediate verification queue

- canonical `npm run dev` now runs the supervised V3 stack, migrates the exact
  `var/kolibri-v3.db` to schema 44 before opening the port, requires the single
  active platform owner and waits for launch-bound `kolibri-v3` backend health
  before starting the web client. A backend exit fences and restarts web until
  that gate passes again, so a stale process on port 8002 cannot be accepted;
  the latest live `32539 → 37862 → 38028` backend crash/restarts repeated
  schema-44 migration and exact `montodays@ya.ru` owner preflight. The backend default
  database is absolute and remains canonical even when the process starts
  from `backend/`;
  V3-scoped agent instructions and the repository development guide now encode
  the same invariant, and the old frontend-only shortcut exits with code `2`;
  restart and browser evidence is in
  `evidence/local-dev-runtime-restart-2026-07-30.md`;
- the isolated identity suite exposed and fixed an eager `chat` package import
  cycle; identity tests now pass independently at `15 passed` without relying
  on full-suite import order;
- the previous owner password credential was restored from the pre-override
  database snapshot after a new rollback copy was created; the owner login
  throttle is empty and six existing owner sessions remain active;
- the complete backend suite is green at `280 passed`;
- deterministic Moscow weather AG-UI trace is proven locally; fresh
  per-profile Safari/live-provider latency samples remain;
- durable image-artifact and bounded-attachment journeys are proven locally;
- full web tests are `128/128`; typecheck and the clean schema-44 production
  package smoke pass;
- Expo static gates, Doctor and both exports pass; simulator/device launch
  remains externally blocked;
- portable release tests are `16/16`; the expanded credential/token scanner
  passes a clean full-tree archive build and verification;
- the packaged release monitor now covers exact public/backend/frontend/worker
  readiness, service failure, error-rate/p95/queue metrics, stuck runs,
  capacity, backup health and TLS expiry with bounded no-secret output. One
  fail-closed renderer supplies the exact monitor and daily verified-backup
  units to both the installer and Linux CI `systemd-analyze`; local negative
  contracts and a fresh clean production smoke pass. Remote Linux green,
  independent external/cellular monitoring and live alert delivery remain;
  see `evidence/local-release-observability-alerts-2026-07-30.md`;
- the portable builder now audits the complete Git commit, rejects committed
  parent-level V3 Home/Primary/bare-metal release helpers, and accepts the
  retired coordinator only as its byte-exact read-only tombstone. CI repeats
  the audit explicitly; see
  `evidence/local-release-lane-audit-2026-07-30.md`;
- the canonical schema-43 development database passed an online backup,
  byte-exact restore, integrity/foreign-key verification and a rolled-back
  write probe. The packaged installer uses that same helper. An isolated clean
  working-tree release preview also passed the complete portable smoke gate;
  see
  `evidence/local-database-backup-restore-rehearsal-2026-07-30.md`;
- Storage Admin control-plane contracts and responsive browser QA pass, but
  destructive mutation remains fail-closed until exhaustive live-reference
  guard evidence. Rust 1.85 fmt/clippy, debug tests `27/27`, release tests
  `27/27` and locked release build pass; independent review found no P0/P1
  for the shipped capacity-only binary. Linux-only mountinfo tests, Home
  enrollment, Primary mTLS and mutation authorization remain open. See
  `evidence/local-storage-admin-control-plane-2026-07-30.md`;
- mobile ChatGPT reference state matrix plus same-state Kolibri comparisons;
- public bearer AG-UI estimate creation now auto-creates its project/thread,
  persists version 1 and binds the durable origin run;
- web dependency audit is `0`; the separate Expo tooling audit remains open;
- isolated clean schema-44 working-tree archive smoke passes through the real
  production Product worker launcher and exact backend/frontend/worker release
  identity. A clean committed RC, immutable-RC rollback, external alert
  delivery and remote CI remain;
- exact owner/migration and backend/frontend/worker release-identity evidence is
  in `evidence/local-owner-migration-release-identity-2026-07-30.md`;
- local workstation capacity recovered from 25 GiB to 48 GiB available before
  the fresh build (45 GiB after it); the release smoke now fails closed below
  10 GiB free.
