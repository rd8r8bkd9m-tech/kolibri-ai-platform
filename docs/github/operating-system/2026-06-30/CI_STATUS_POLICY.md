# CI Status Policy

## Required Checks For `main`

- `Kolibri CI / ci` must pass before merge.
- Secret scan must pass.
- Production secret path guard must pass.
- Python compile and pytest must pass when Python code/tests exist.
- Frontend build/lint/typecheck/test must pass when frontend scripts exist.

## Docs-Only PRs

Docs-only PRs still require:

- `git diff --check`;
- Markdown/YAML/JSON validity where applicable;
- CI green or clear explanation if CI is not triggered.

## Backend/Control Plane/Agent Host PRs

Require focused tests plus full CI. Runner/Control Plane PRs must include contract tests for task states, artifacts, write scope and failure reporting.

## Frontend/PWA PRs

Require build and, when UI changes are visible, screenshots or browser artifacts.

## Security/Secrets

Any PR touching auth, env handling, credentials, keys or payment must be `risk:high` or `risk:dangerous` and requires owner approval.

## Recent CI Note

Recent run `28443763496` failed on branch `codex/kol-home-cluster-20260629-141939-009-main-codex`; GitHub Curator should classify or link it to a fix/ignore decision.
