# Phase 2 Start: Controlled Release & Deploy Preparation

Date: 2026-07-05

## Git Checkpoint

- Branch: `p0/codex-sidebar-thread-bootstrap-20260704`
- Commit: `e8f36fdc7`
- Worktree: `/Users/kolibri/Documents/Codex/kolibri-ai-platform`

## Phase 1 Completed

- Initial state, policy, source of truth, project map, V1 architecture, repo cleanup plan, Control Plane foundation, agent model, GitHub presentation, GitHub Pages prep, checks, and final report.

## Phase 1 Checks Passed

```bash
jq empty release/manifest.json .vscode/tasks.json .vscode/settings.json .vscode/extensions.json
backend/venv/bin/python -m pytest -q tests/test_factory_control_superfactory.py tests/test_telegram_superfactory_miniapp.py tests/test_telegram_superfactory_contracts.py
```

Result: `8 passed`.

## Intentionally Not Done

- DNS/REG.RU changes.
- Production deploy.
- Destructive bootstrap.
- Server/firewall changes.
- Secret rotation.
- Force push/history rewrite.
- Data deletion.

## Phase 2 Scope

- Public/secret hygiene check.
- GitHub presentation polish.
- GitHub Pages readiness check.
- Control Plane and agent runtime status/gap reports.
- Expanded safe checks.
- Commit checkpoint preparation.
- Deploy plan with approval gates.

## Requires USER_APPROVAL

- Push current branch to GitHub.
- Run/enable GitHub Pages publication if it mutates repository settings.
- Change REG.RU/DNS records for `kolibriai.ru`.
- Deploy backend to `api.kolibriai.ru`.
- Run protected bootstrap.
