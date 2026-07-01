# PR Review Policy

## Risk Levels

- `risk:low`: docs-only, templates, no runtime behavior.
- `risk:medium`: isolated code path with tests and rollback.
- `risk:high`: backend, Control Plane, Agent Host, billing, auth, deployment, data migration, Telegram production path.
- `risk:dangerous`: secrets, payments, destructive admin operations, infrastructure-wide restart, branch protection changes.

## Required Review By Area

- `ops/`: owner or trusted factory reviewer.
- `backend/`: backend/API reviewer.
- `frontend/`: frontend/PWA reviewer.
- `infra/`: DevOps/security reviewer.
- `scripts/training/`: model factory reviewer.
- `.github/`: GitHub Curator plus owner for write workflows.
- `docs/superfactory/` and `docs/agent/`: owner-visible docs reviewer.

## PR #46 Rule

PR #46 must not be merged as-is. It must be split into separate PRs for:

- PWA/frontend;
- billing;
- factory contracts/runner;
- deterministic estimates;
- FormulaLM harness;
- docs/artifacts.

## Ready Labels

Use `status:ready` only when tests, CI, scope, risk, rollback and artifacts are all present.
