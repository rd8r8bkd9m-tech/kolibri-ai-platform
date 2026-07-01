# P0 Split PR #46 Into Safe PRs

## Context

PR #46 mixes PWA, billing, factory autonomy, runner, deterministic estimates, FormulaLM and docs.

## Scope

Create focused PRs for:

- PWA/frontend;
- billing;
- factory contracts/runner;
- deterministic estimates;
- FormulaLM harness;
- docs/artifacts.

## Acceptance

- Each split PR has tests, risk, rollback and artifact links.
- No secrets/payment credentials are committed.
- Original PR #46 remains draft until split is complete.

## Forbidden

- No merge of PR #46 as-is.
- No product/billing/runtime mixing in a single replacement PR.
