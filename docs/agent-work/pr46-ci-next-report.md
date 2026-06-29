# PR #46 CI next report

Date: 2026-06-29
Role: CI/PR operator
Workspace: `/Users/kolibri/.codex/worktrees/6ff4/kolibri-ai-platform`
PR: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/46

## Remote PR state

- PR #46 is open and draft.
- Title: `[codex] Factory autonomy, PWA billing, remote FormulaLM`
- Base: `main`
- Head branch: `codex/factory-autonomy-pwa-billing`
- Head SHA: `eadc04a07ca51812615f8b523c828d0fff1c136f`
- Mergeability from GitHub: `MERGEABLE`

## GitHub checks

`gh pr checks 46` still reports two failed `Kolibri CI / ci` checks for the same head SHA:

- Pull request run: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/actions/runs/28346987211/job/83972253483
- Push run: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/actions/runs/28346968290/job/83972196451

Both failures stop in the `Pytest tests` step before Node, JSON/YAML validation, secret scan, production secret path guard, or smoke checks run.

Failure:

```text
FAILED tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint
assert "Фабрика Колибри" in app_source
1 failed, 68 passed, 1 warning
```

The failed remote SHA has `frontend/src/App.jsx` using `/api/factory/status`, but it does not contain the expected source-level product label `Фабрика Колибри`.

## Local blocker status

The current local worktree already contains an uncommitted/unpushed candidate fix:

- `frontend/src/App.jsx` defines `PRODUCT_TITLE = "Фабрика Колибри"`.
- `frontend/src/App.jsx` passes `productTitle={PRODUCT_TITLE}` into app and landing header paths.
- `frontend/src/components/AppHeader.jsx` renders `productTitle`.

That means the remote CI failure is still real for PR #46, but the local workspace no longer reproduces that failure.

## Local checks run

Python:

```text
/opt/homebrew/bin/python3.12 -m compileall -q backend infra scripts
passed

/tmp/kolibri-pr46-ci-venv/bin/python -m pytest -q
89 passed, 1 warning in 27.38s
```

Frontend:

```text
npm run build
passed; Vite emitted only the existing chunk-size warning for a 512.29 kB JS asset

npm run lint
passed with 3 warnings and 0 errors

npm run test:mobile-layout
mobile layout guard passed
```

CI tail guards reproduced locally:

```text
validated 12 tracked JSON files
validated 1 tracked YAML files
secret scan passed across 112 tracked files
production secret path guard passed for origin/main...HEAD (56 committed changed files)
backend smoke passed
frontend smoke passed
```

Extra local safety check for currently untracked JSON files:

```text
validated 21 workspace JSON files excluding node_modules/.git/dist
```

## Local operational blockers

No code/test blocker remains for the observed remote pytest failure.

Operational blocker before any push:

- The worktree is dirty and includes many existing modified and untracked files that are not mine.
- Do not stage/push blindly from this workspace.
- The minimal CI-unblock payload must include the product-title fix in `frontend/src/App.jsx` plus the corresponding header rendering in `frontend/src/components/AppHeader.jsx`; review the wider frontend changes before deciding the exact commit scope.

Additional local environment note:

- Default `python3` is Python 3.14.4.
- CI uses Python 3.12.
- Use `/opt/homebrew/bin/python3.12` or the temporary `/tmp/kolibri-pr46-ci-venv` style environment for faithful local pytest runs.

## Next action

Push is intentionally not performed.

Recommended next operator step:

1. Isolate and review the intended PR #46 local diff.
2. Stage only the approved files.
3. Push the fix branch.
4. Re-run or watch PR #46 checks with `gh pr checks 46 --watch`.
