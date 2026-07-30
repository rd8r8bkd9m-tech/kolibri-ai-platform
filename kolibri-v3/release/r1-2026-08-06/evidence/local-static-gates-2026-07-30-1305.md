# Local static gates — 2026-07-30 13:05 MSK

Candidate state: dirty development tree on `codex/v3-home-deploy`.

This record is not RC evidence. It records reproducible local checks before
the clean candidate is created.

## Toolchain

- Node.js: `v24.18.0`
- npm: `11.16.0`
- Python: `3.14.6`
- Rust: `rustc 1.85.0 (4d91de4e4 2025-02-17)`

## Web

- `npm test`: 97 passed.
- `npm run typecheck`: passed.
- Latest long-press touch replay:
  `docs/design-evidence/mobile-comparison/long-press-acceptance.md`.
- Production build must be repeated after the active auth/runtime/release
  changes settle.

## Product backend

- Last complete suite before the active direct-run/auth changes: 222 passed.
- Local backend health:
  `GET http://127.0.0.1:8002/v1/health` returned
  `{"status":"ok","service":"kolibri-v3"}`.
- The suite must be repeated after migration 039 and bearer AG-UI integration.

## Contracts and portable release

- `python server/generate_contract_manifest.py --check`: passed.
- `node tests/portable-release.test.mjs`: 10 passed.
- The canonical release-lane audit is still active; these results do not
  replace a clean-checkout archive smoke.

## Rust estimate kernel

Commands use the pinned R1 compiler:

```text
cargo +1.85.0 fmt --check
cargo +1.85.0 test
cargo +1.85.0 clippy --all-targets -- -D warnings
```

Results:

- 5 unit tests passed.
- 1 shared golden-contract test passed.
- doc tests passed.
- clippy passed with warnings denied.

The Rust kernel remains shadow/conformance-only. Python/server remains the
authoritative R1 calculation path.

## Expo / React Native

- Native contract tests: 5 passed.
- TypeScript: passed.
- Expo lint: passed; only the existing legacy-config/npm warning was emitted.
- Expo Doctor: 20/20 passed.
- iOS export: passed, Hermes bundle 5.7 MB.
- Android export: passed, Hermes bundle 5.9 MB.
- Both exports include all 10 active and 10 thumbnail pet assets.

Runtime launch remains blocked by the absence of an available iOS Simulator,
Android emulator or attached automation-capable physical device.

## Local service snapshot

- Next development surface: `127.0.0.1:3103`, HTTP 200.
- Product API: `127.0.0.1:8002`, healthy.
- MiMo runtime and Codex app-server are process-persistent children of the
  Product API lifespan. Their current process lifetime began with the last
  development backend restart.
- `/api/health` returns release ID `unversioned`, as expected for the
  development process. An immutable candidate must inject a real release ID.
