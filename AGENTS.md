# KolibriAI Platform Agent Handoff

Owner directive date: 2026-07-05.

This branch is the active FastAPI/React/Fabric/Superfactory product workspace. It must stay aligned with Calibri V1 policy while preserving current runtime contracts.

## Active Workspace

- Worktree: `/Users/kolibri/Documents/Codex/kolibri-ai-platform`
- Branch: `p0/codex-sidebar-thread-bootstrap-20260704`
- HEAD at initial capture: `e8f36fdc7`
- Related Rust foundation worktree: `/Users/kolibri/.codex/worktrees/b56d/kolibri-ai-platform`

## Read First

1. `.kolibri/AGENT_START_HERE.md`
2. `.kolibri/LEAD_AGENT_ACCESS_POLICY.md`
3. `docs/SOURCE_OF_TRUTH.md`
4. `docs/PROJECT_MAP.md`
5. `docs/CONTROL_PLANE_AGENT_MODEL.md`
6. `docs/BOOTSTRAP_TRUTH.md`
7. `README.md`

## Current Verified Slice

Use `backend/venv/bin/python` for pytest in this branch.

```bash
backend/venv/bin/python -m pytest -q tests/test_factory_control_superfactory.py tests/test_telegram_superfactory_miniapp.py tests/test_telegram_superfactory_contracts.py
```

At handoff time this Superfactory slice passed: `8 passed`.

## Safety

- Do not read or commit `ops/telegram.env`.
- Do not log raw secrets.
- Do not run production deploy, bootstrap, DNS, REG.RU, firewall, server reboot/reinstall, or destructive data operations without approval.
- Do not discard untracked runtime artifacts without approval.
- Worker agents must use API contracts, not SSH.
