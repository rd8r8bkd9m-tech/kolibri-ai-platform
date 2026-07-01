# P0 Agent Host Generic Runner Contract Hardening

## Context

Remote tasks produced useful work but were marked failed because required artifact paths were missing or verifier behavior was too weak.

## Scope

- Exact artifact path enforcement.
- write_scope enforcement.
- read-only/no-push/product-code guards.
- structured blocked/failed/completed results.
- tests for unsupported task kinds and missing artifacts.

## Acceptance

- Agent cannot report completed if required files are missing.
- Useful work is preserved and linked even on verifier failure.
- CI and server validation pass.

## Forbidden

- No weakening safety gates.
- No broad unrelated refactor.
