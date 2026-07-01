# Contributing To Kolibri Factory

## Source Of Truth

GitHub is the source of truth for branches, PRs, issues, CI, releases and durable project state. Control Plane and Agent Host execute work remotely, but every durable result must be linked back to GitHub.

## Branches

Use focused branches:

- `p0/<topic>-YYYY-MM-DD`
- `p1/<topic>-YYYY-MM-DD`
- `docs/<topic>`
- `fix/<topic>`
- `feature/<topic>`
- `agent/<task-id>/<topic>`
- `research/<topic>`

Do not push directly to `main`. Do not force push. Do not mix unrelated subsystems in one PR.

## Pull Requests

Every PR must include scope, non-scope, linked issue/task_id, tests, CI status, risk, rollback plan and artifact links. Draft PRs are allowed for remote agent output, but they are not merge-ready until the PR template gate is satisfied.

## Remote-First Work

Mac is a command center. Heavy tests, server validation, model work, FormulaLM, image generation, fleet operations and production-like checks should run on remote servers, Control Plane, Agent Host or GitHub Actions.

## Safety

No secrets in logs or commits. No destructive operations without owner approval. No automatic money movement, account registration, security bypass or provider limit abuse.
