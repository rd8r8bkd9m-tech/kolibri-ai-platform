# Worktree cleanup staging package

Date: 2026-06-29
Scope: `/Users/kolibri/.codex/worktrees/6ff4/kolibri-ai-platform`

This package is a preview only. It does not delete files, stage changes, commit, or push.

## Current categories

### commit_p0_runtime

Runtime, billing, factory control, Telegram gateway, desktop control contracts, factory envelopes, and contract tests:

```bash
git add \
  backend/billing.py \
  backend/desktop_control_contracts.py \
  backend/tests/test_billing.py \
  ops/agent_host.py \
  ops/factory_control.py \
  ops/factory_role_catalog.json \
  ops/telegram_gateway.py \
  ops/envelopes/KOL-DESKTOP-CONTROL-APP-MVP-20260629.json \
  ops/envelopes/KOL-DOCS-STEWARD-20260629.json \
  ops/envelopes/KOL-FORMULALM-REMOTE-BENCH-6H-20260629.json \
  ops/envelopes/KOL-GITHUB-PROJECT-OPS-20260629.json \
  ops/envelopes/KOL-INVESTOR-OUTREACH-20260629.json \
  ops/envelopes/KOL-LIVING-BIRD-RD-20260629.json \
  ops/envelopes/KOL-P0-APP-QUEUE-UNBLOCK-20260629.json \
  ops/envelopes/KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629.json \
  ops/envelopes/KOL-PREMIUM-LANDING-UI-20260629.json \
  ops/envelopes/KOL-PRODUCT-QA-E2E-20260629.json \
  ops/envelopes/KOL-SUBAGENT-POOL-SUPERVISOR-20260629.json \
  tests/test_desktop_control_contracts.py \
  tests/test_factory_agent_messages.py \
  tests/test_factory_runtime_queue_contracts.py \
  tests/test_telegram_gateway.py
```

### commit_frontend

PWA metadata, landing shell, living bird UI, responsive chat/control surface, lint config, and landing image asset:

```bash
git add \
  frontend/eslint.config.js \
  frontend/index.html \
  frontend/public/manifest.webmanifest \
  frontend/src/App.css \
  frontend/src/App.jsx \
  frontend/src/assets/landing-hero.png \
  frontend/src/components/AppHeader.jsx \
  frontend/src/components/KolibriBird.jsx \
  frontend/src/components/LandingShell.jsx \
  frontend/src/components/LivingKolibri.jsx \
  frontend/src/components/chat/ChatComposer.jsx \
  frontend/src/components/chat/ChatWorkspace.jsx \
  frontend/src/components/control/ControlFab.jsx \
  frontend/src/components/control/ControlPanel.jsx
```

### commit_docs

Repository documentation, agent-work reports, ops watch notes, and this cleanup preview helper:

```bash
git add \
  README.md \
  docs/ \
  ops/hourly-sync-report.md \
  ops/secondary-control-plane-watchdog.md \
  scripts/worktree_cleanup_preview.sh
```

## exclude_generated

Do not commit local Playwright CLI capture output:

```text
.playwright-cli/
```

## candidate_delete_unused

Preview only. These files are generated local browser captures and can be removed manually if no longer needed:

```bash
rm -v \
  .playwright-cli/console-2026-06-29T05-20-02-577Z.log \
  .playwright-cli/console-2026-06-29T05-21-00-297Z.log \
  .playwright-cli/console-2026-06-29T05-22-22-535Z.log \
  .playwright-cli/console-2026-06-29T05-23-47-522Z.log \
  .playwright-cli/console-2026-06-29T05-24-58-986Z.log \
  .playwright-cli/console-2026-06-29T05-26-34-160Z.log \
  .playwright-cli/console-2026-06-29T05-28-34-186Z.log \
  .playwright-cli/page-2026-06-29T05-20-07-838Z.yml \
  .playwright-cli/page-2026-06-29T05-21-02-769Z.yml \
  .playwright-cli/page-2026-06-29T05-22-29-819Z.yml \
  .playwright-cli/page-2026-06-29T05-23-51-201Z.yml \
  .playwright-cli/page-2026-06-29T05-25-05-435Z.yml \
  .playwright-cli/page-2026-06-29T05-26-45-784Z.yml \
  .playwright-cli/page-2026-06-29T05-28-54-068Z.yml
```

## Verification commands

```bash
bash scripts/worktree_cleanup_preview.sh
git status --short -uall
```

Expected result: the script prints the five categories and preview commands only. `git status` should still show unstaged/untracked files because this package intentionally does not stage or delete anything.
