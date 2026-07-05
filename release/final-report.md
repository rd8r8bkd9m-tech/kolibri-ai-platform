# KolibriAI Platform / Calibri V1 Transition Report

Date: 2026-07-05

## Branch

- Worktree: `/Users/kolibri/Documents/Codex/kolibri-ai-platform`
- Branch: `p0/codex-sidebar-thread-bootstrap-20260704`
- HEAD at initial capture: `e8f36fdc7`

## What Changed

- Added branch-local agent policy and onboarding under `.kolibri/`.
- Added root `AGENTS.md` for future agents.
- Added source-of-truth docs for this FastAPI/React/Fabric/Superfactory branch:
  - `docs/SOURCE_OF_TRUTH.md`
  - `docs/PROJECT_MAP.md`
  - `docs/CALIBRI_V1_ARCHITECTURE.md`
  - `docs/CONTROL_PLANE_FOUNDATION.md`
  - `docs/CONTROL_PLANE_AGENT_MODEL.md`
  - `docs/API_COMPATIBILITY_MAP.md`
  - `docs/BOOTSTRAP_TRUTH.md`
  - `docs/REPO_CLEANUP_PLAN.md`
  - `docs/CONFLICTS.md`
- Captured branch initial state in `release/initial-state.md`.
- Captured raw git status in `release/initial-git-status.txt`.
- Added public/GitHub presentation docs:
  - `docs/INVESTOR_OVERVIEW.md`
  - `docs/ARCHITECTURE_PUBLIC.md`
  - `docs/ROADMAP.md`
  - `docs/SECURITY_PUBLIC.md`
  - `docs/GITHUB_PRESENTATION.md`
  - `docs/GITHUB_PROJECT_PLAN.md`
  - `docs/SERVER_INVENTORY_PUBLIC.md`
- Added development and release entrypoints:
  - `docs/DEVELOPMENT.md`
  - `docs/RELEASE_PROCESS.md`
- Added GitHub Pages preparation:
  - `docs/deployment-github-pages.md`
  - `release/pages-status.md`
- Added private ops examples:
  - `ops/README.md`
  - `ops/SERVER_INVENTORY.private.example.md`
  - `ops/BOOTSTRAP_NOTES.private.example.md`
- Added GitHub templates and project-local VS Code tasks.
- Added `VERSION`, `release/checklist.md`, and `release/manifest.json`.
- Updated `.gitignore` to keep private/runtime outputs out of status:
  - `.env.*` with `!.env.example`
  - `ops/*.env`
  - `ops/*.private.md`
  - `*.secret`, `*.key`
  - `logs/`, `output/`, `server.pid`
  - `frontend/storybook-static/`, `frontend/test-results/`

## Validation

```bash
backend/venv/bin/python -m pytest -q tests/test_factory_control_superfactory.py tests/test_telegram_superfactory_miniapp.py tests/test_telegram_superfactory_contracts.py
```

Result: `8 passed`.

```bash
backend/venv/bin/python -m compileall -q ops/factory_control.py ops/telegram_superfactory.py tests/test_factory_control_superfactory.py
```

Result: passed.

```bash
jq empty release/manifest.json .vscode/tasks.json .vscode/settings.json .vscode/extensions.json
```

Result: passed.

## Requirement Coverage

- Initial state: done.
- Policy: done.
- Source of truth: done.
- Project map: done.
- V1 architecture: done.
- Repo cleanup: done as non-destructive ignore rules and cleanup plan.
- Control Plane foundation: done as transition documentation.
- Agent model: done.
- GitHub presentation: done.
- Site/GitHub Pages prep: done without DNS changes.
- Checks: done for Superfactory slice and JSON configs.
- Final report: done.

## Safety Notes

- `ops/telegram.env` was not read or printed.
- No DNS, REG.RU, production deploy, bootstrap, firewall, server restart, or destructive command was run.
- Related Rust foundation remains in `/Users/kolibri/.codex/worktrees/b56d/kolibri-ai-platform` and was not merged into this branch.

## Remaining State

Untracked items still visible after private/runtime ignore:

- `.kolibri/`
- `AGENTS.md`
- `apps/`
- `docs/BOOTSTRAP_TRUTH.md`
- `docs/CALIBRI_V1_ARCHITECTURE.md`
- `docs/CONTROL_PLANE_FOUNDATION.md`
- `docs/CONTROL_PLANE_AGENT_MODEL.md`
- `docs/GITHUB_PRESENTATION.md`
- `docs/PROJECT_MAP.md`
- `docs/SOURCE_OF_TRUTH.md`
- `release/checklist.md`
- `release/initial-state.md`
- `release/manifest.json`
- `tests/test_kolibri_invention_synthesis.py`

Do not discard them without owner approval.

# Phase 2: Controlled Release Candidate

## What was verified

- Public-file secret scan: `checked_public_files=543`, `findings=0`.
- JSON configs: passed.
- Python compileall for `backend`, `ops`, `scripts`: passed.
- Superfactory/Fabric focused slice: `14 passed`.
- Full pytest suite: `210 passed`.
- Frontend GitHub Pages build: passed with a non-fatal Vite chunk-size warning.
- Docker compose config: skipped because no compose file was found.
- Cargo checks: skipped because this active branch has no `Cargo.toml`.

## What was changed

- README was rewritten as a public release-candidate product presentation.
- `.gitignore` was strengthened for `.pem`, explicit `ops/telegram.env`, `secrets/`, and `credentials/`.
- `docs/API_COMPATIBILITY_MAP.md` now maps desired Calibri V1 endpoints to current Fabric/Superfactory contracts.
- Phase 2 release artifacts were added:
  - `release/phase-2-start.md`
  - `release/security-publication-check.md`
  - `release/control-plane-status.md`
  - `release/agent-runtime-status.md`
  - `release/deploy-plan.md`
  - `release/check-results-phase-2.md`
  - `release/git-checkpoint.md`
  - `release/phase-2-summary.md`

## GitHub presentation status

Ready as a release-candidate presentation. The README now describes product pitch, AI Factory model, architecture, Calibri V1 status, quickstart, roadmap, security, docs, `kolibriai.ru` planned status, and release status.

## GitHub Pages status

Prepared, not deployed by this pass. Existing workflow: `.github/workflows/pages.yml`. Site source: `frontend`. Build command: `npm run build`. Output: `frontend/dist`. CNAME: `frontend/CNAME` with `kolibriai.ru`.

## Control Plane status

Partial. Current working surface is FastAPI backend plus Fabric/Superfactory sidecars. Desired `/v1/status`, `/v1/agents`, `/v1/tasks`, `/v1/artifacts`, and `/v1/approvals` are mapped in `docs/API_COMPATIBILITY_MAP.md`; missing endpoints were recorded as gaps rather than risky rewrites.

## Agent Runtime status

Partial. `ops/agent_host.py` and Fabric/Superfactory tests cover task envelopes, runner policy, artifacts, permission behavior, and deny-by-default stubs. Enroll/events/approval endpoints need focused compatibility work.

## Security/publication check

No secret findings in scanned public files. `.env`, `.env.*`, `ops/*.env`, `ops/telegram.env`, private keys, secrets, credentials, logs, output, and generated frontend reports are protected by ignore rules. `ops/telegram.env` was not read or printed.

## Tests/checks

See `release/check-results-phase-2.md` for exact commands and results.

## Commit/checkpoint status

Commit checkpoint prepared in `release/git-checkpoint.md`. Staging must exclude `apps/`, `tests/test_kolibri_invention_synthesis.py`, `.env*`, `ops/telegram.env`, private keys, secrets, logs, and runtime outputs unless separately reviewed.

## Deploy readiness

Deploy plan is ready in `release/deploy-plan.md`. No deploy was performed. GitHub Pages, DNS, API backend deploy, and bootstrap are approval-gated.

## Required approvals

- Push current branch to GitHub.
- Enable/run GitHub Pages publication if repository settings or deployment are changed.
- Change REG.RU/DNS for `kolibriai.ru`.
- Deploy backend to `api.kolibriai.ru`.
- Run protected bootstrap.

## Next exact actions

1. Review staged file list in `release/git-checkpoint.md`.
2. Stage only release-candidate files.
3. Run staged secret/path checks.
4. Commit with `chore(calibri-v1): establish release candidate foundation` if approved and safe.
5. Ask for explicit approval before push, Pages deploy, DNS, API deploy, or bootstrap.
