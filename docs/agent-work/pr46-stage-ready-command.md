# PR #46 first P0 commit: ready stage/commit/push command

Дата: 2026-06-29.
Ветка: `codex/factory-autonomy-pwa-billing`.
Режим: command file only. Этот документ не выполняет staging, commit или push.

## Проверки выполнены

```bash
git status --short
rg -n 'Фабрика Колибри' frontend/src/App.jsx
/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_runtime_queue_contracts.py tests/test_factory_status.py || true
git diff --check
```

Результат:

- `frontend/src/App.jsx:14` содержит `const PRODUCT_TITLE = "Фабрика Колибри"`.
- P0 runtime/frontend guard tests: `7 passed in 0.92s`.
- `git diff --check` завершился без замечаний.

## Stage groups

### P0 runtime

- `ops/factory_control.py`
- `ops/agent_host.py`
- `tests/test_factory_runtime_queue_contracts.py`
- `tests/test_factory_agent_messages.py`

### P0 frontend / CI guard

- `frontend/index.html`
- `frontend/public/manifest.webmanifest`
- `frontend/eslint.config.js`
- `frontend/src/App.css`
- `frontend/src/App.jsx`
- `frontend/src/components/AppHeader.jsx`
- `frontend/src/components/KolibriBird.jsx`
- `frontend/src/components/LandingShell.jsx`
- `frontend/src/components/LivingKolibri.jsx`
- `frontend/src/components/chat/ChatComposer.jsx`
- `frontend/src/components/chat/ChatWorkspace.jsx`
- `frontend/src/components/control/ControlFab.jsx`
- `frontend/src/components/control/ControlPanel.jsx`

### P0 docs / envelopes

- `docs/agent-work/pr46-stage-ready-command.md`
- `docs/agent-work/ci-failure-triage.md`
- `docs/agent-work/pr46-ci-next-report.md`
- `docs/agent-work/control-plane-queue-unblock-report.md`
- `docs/agent-work/factory-p0-live-repair-status.md`
- `docs/agent-work/p0-runtime-watch-report.md`
- `ops/envelopes/KOL-P0-APP-QUEUE-UNBLOCK-20260629.json`
- `ops/envelopes/KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629.json`

## Single git add command

```bash
git add ops/factory_control.py ops/agent_host.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_agent_messages.py frontend/index.html frontend/public/manifest.webmanifest frontend/eslint.config.js frontend/src/App.css frontend/src/App.jsx frontend/src/components/AppHeader.jsx frontend/src/components/KolibriBird.jsx frontend/src/components/LandingShell.jsx frontend/src/components/LivingKolibri.jsx frontend/src/components/chat/ChatComposer.jsx frontend/src/components/chat/ChatWorkspace.jsx frontend/src/components/control/ControlFab.jsx frontend/src/components/control/ControlPanel.jsx docs/agent-work/pr46-stage-ready-command.md docs/agent-work/ci-failure-triage.md docs/agent-work/pr46-ci-next-report.md docs/agent-work/control-plane-queue-unblock-report.md docs/agent-work/factory-p0-live-repair-status.md docs/agent-work/p0-runtime-watch-report.md ops/envelopes/KOL-P0-APP-QUEUE-UNBLOCK-20260629.json ops/envelopes/KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629.json
```

## Commit command

```bash
git commit -m "factory: restore p0 runtime visibility and frontend guard"
```

Commit message:

```text
factory: restore p0 runtime visibility and frontend guard
```

## Push command

```bash
git push origin codex/factory-autonomy-pwa-billing
```

## Excluded from first P0 commit

- `.playwright-cli/page-*.yml`: generated local Playwright snapshots.
- `.playwright-cli/console-*.log`: generated logs, already ignored.
- `frontend/src/assets/landing-hero.png`: unused/orphan asset; `rg -n "landing-hero" frontend/src frontend/index.html frontend/public` finds only CSS class names, no asset import.
- `backend/billing.py`, `backend/tests/test_billing.py`: billing slice, separate commit.
- `ops/telegram_gateway.py`, `tests/test_telegram_gateway.py`: Telegram report CLI slice, separate commit.
- `backend/desktop_control_contracts.py`, `tests/test_desktop_control_contracts.py`: desktop-control contract slice, separate commit.
- `README.md`, `docs/README.md`, `docs/API-RU.md`, broad `docs/` portal files: docs portal slice, separate commit.
- `ops/factory_role_catalog.json` and non-P0 envelopes: factory planning slice, separate commit.
- `scripts/worktree_cleanup_preview.sh`, `docs/agent-work/worktree-cleanup-staging-report.md`, `docs/agent-work/pr46-staging-plan.md`: staging/cleanup helper artifacts, not needed in first P0 commit.

## Pre-run safety checklist

Перед запуском команд выше:

```bash
git status --short
rg -n 'Фабрика Колибри' frontend/src/App.jsx
/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_runtime_queue_contracts.py tests/test_factory_status.py
git diff --check
```

После `git add`, но до `git commit`, проверить staged scope:

```bash
git diff --cached --name-only
git diff --cached --check
```
