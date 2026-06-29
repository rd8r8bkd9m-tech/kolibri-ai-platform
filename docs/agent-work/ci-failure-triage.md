# CI failure triage: PR #46

Date: 2026-06-29
Role: ci_failure_triage_agent
PR: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/46
Head SHA: `eadc04a07ca51812615f8b523c828d0fff1c136f`
Branch: `codex/factory-autonomy-pwa-billing`

## Failing checks

Both failing checks are the same GitHub Actions workflow/job on the same SHA:

- `Kolibri CI / ci`, event `pull_request`, run `28346987211`, job `83972253483`, failed at `2026-06-29T03:37:46Z`
  - Job URL: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/actions/runs/28346987211/job/83972253483
- `Kolibri CI / ci`, event `push`, run `28346968290`, job `83972196451`, failed at `2026-06-29T03:37:03Z`
  - Job URL: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/actions/runs/28346968290/job/83972196451

The failing step is `Pytest tests`. Later steps (`Set up Node`, JavaScript checks, JSON/YAML validation, secret scan, smoke) were skipped because pytest exited non-zero.

## Root cause

`tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint` reads only `frontend/src/App.jsx` and asserts that the source still contains the product label `Фабрика Колибри`.

At the failed CI SHA, `App.jsx` did contain the live endpoint `/api/factory/status` and did not contain the old `/cluster/status` or static `на базе 5 серверов` text, but it no longer contained `Фабрика Колибри`. The frontend refactor extracted UI into components and left the expected product title out of `App.jsx`, so the source-level regression guard failed.

Relevant log snippet from both runs:

```text
FAILED tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint
>       assert "Фабрика Колибри" in app_source
E       assert 'Фабрика Колибри' in 'import { useCallback, useEffect, useMemo, useRef, useState } from "react"\n...'
1 failed, 68 passed, 1 warning
```

## Commands used

GitHub Actions inspection:

```bash
gh auth status
gh pr view 46 --json number,url,title,headRefName,headRefOid,baseRefName,statusCheckRollup
gh pr checks 46 --json name,state,bucket,link,startedAt,completedAt,workflow
gh run view 28346987211 --json databaseId,name,workflowName,conclusion,status,url,event,headBranch,headSha,createdAt,updatedAt,jobs
gh run view 28346968290 --json databaseId,name,workflowName,conclusion,status,url,event,headBranch,headSha,createdAt,updatedAt,jobs
gh run view 28346987211 --log | rg -C 6 "FAILED tests/test_factory_status.py|test_frontend_uses_live_factory_status_endpoint|Фабрика Колибри|1 failed"
gh run view 28346968290 --log | rg -C 6 "FAILED tests/test_factory_status.py|test_frontend_uses_live_factory_status_endpoint|Фабрика Колибри|1 failed"
```

Local reproduction command matching the CI failure mode:

```bash
python -m pytest tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint -q
```

Local verification in this worktree used Python 3.12 to match Actions:

```bash
/opt/homebrew/bin/python3.12 -m venv /tmp/kolibri-ci-triage-312-venv
/tmp/kolibri-ci-triage-312-venv/bin/python -m pip install -r backend/requirements.txt pytest
/tmp/kolibri-ci-triage-312-venv/bin/python -m pytest tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint -q
/tmp/kolibri-ci-triage-312-venv/bin/python -m pytest tests/test_factory_status.py -q
```

Current local result after the existing uncommitted frontend change:

```text
tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint: 1 passed
tests/test_factory_status.py: 2 passed
```

Note: the default local `python3` is Python 3.14 and cannot install the pinned `pydantic-core==2.23.2` cleanly; this is a local interpreter mismatch, not the CI root cause. GitHub Actions used Python 3.12.13.

## Fix plan

1. Keep the fix narrow: restore the expected product label in the frontend source rather than changing CI config.
2. Prefer a real UI-visible title over a test-only string. The current worktree already has an uncommitted narrow candidate:
   - `frontend/src/App.jsx`: defines `PRODUCT_TITLE = "Фабрика Колибри"` and passes it to `AppHeader`.
   - `frontend/src/components/AppHeader.jsx`: renders `productTitle`.
3. Re-run the targeted test and then the CI pytest command:

```bash
python -m pytest tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint -q
python -m pytest -q
```

4. Push the fix branch and re-run/check PR #46:

```bash
gh pr checks 46 --watch
```

## Code fix needed?

Yes, the failed SHA needs a frontend code fix, not a CI config fix. No additional test/config patch is required for the observed failure. In the current local worktree, a narrow frontend fix already appears to be present but uncommitted/unpushed relative to the failed GitHub Actions run.
