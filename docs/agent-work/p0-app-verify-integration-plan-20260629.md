# P0 App Verify Integration Plan, 2026-06-29

Task: `KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629`
Remote branch: `agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify`
Remote commit: `0e7dc0011063740375ce21153aa72abaca197c2b`
Local HEAD during review: `4fd32d3d514f122dc04a4b4b0c7c28f775f0f4d5`
Merge base: `a009c067fa33670b8aa2837befd0562d1e248805`

## Verdict

`READY_FOR_REVIEW`

The remote branch is available on `origin` and points to the requested commit.
No merge, rebase, cherry-pick, deploy, queue mutation, or code change was
performed by this integration review.

## Remote Availability

Command run:

```bash
git ls-remote origin agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify
```

Observed result:

```text
0e7dc0011063740375ce21153aa72abaca197c2b refs/heads/agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify
```

## Changed Files From Current HEAD

Command run after fetch:

```bash
git diff --name-status HEAD..origin/agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify
```

Observed result:

```text
M docs/agent-work/factory-p0-live-repair-status.md
A docs/agent-work/p0-app-queue-unblock-verify-result.md
D docs/agent-work/telegram-factory-status-letter-20260629.md
M frontend/src/App.jsx
D ops/envelopes/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629.json
M tests/test_factory_status.py
```

Important integration note: the branch itself, relative to merge base
`a009c067fa33670b8aa2837befd0562d1e248805`, changes only:

```text
A docs/agent-work/p0-app-queue-unblock-verify-result.md
M frontend/src/App.jsx
M tests/test_factory_status.py
```

The apparent deletions in `HEAD..origin/<branch>` are caused by the current
local HEAD being one commit ahead of the branch base:

```text
M docs/agent-work/factory-p0-live-repair-status.md
A docs/agent-work/telegram-factory-status-letter-20260629.md
A ops/envelopes/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629.json
```

Main executor should review these as integration overlap, not as proof that the
remote branch intentionally removes all newer local artifacts.

## Machine Review Summary

- `frontend/src/App.jsx` adds `FACTORY_STATUS_ENDPOINTS` and changes factory
  status loading to try `/api/factory/status` first, then `/cluster/status`
  when the primary route fails or returns non-OK.
- `tests/test_factory_status.py` updates the frontend source contract to require
  `/cluster/status` instead of forbidding it.
- `docs/agent-work/p0-app-queue-unblock-verify-result.md` records the remote
  runner verification result, including passed frontend dependency install,
  lint, build, mobile layout guard, compile checks, and a production deploy
  blocker due to missing explicit deploy authorization/credentials.
- `git diff --check HEAD..origin/<branch>` returned clean output.

Primary review risks:

- The fallback catches all fetch failures and silently tries the alias route.
  This is acceptable for read-only status rendering, but the executor should
  confirm that this behavior is desired for auth/network failures and not only
  for `404`/route absence.
- The focused Python test in the branch is a source-string contract. It verifies
  endpoint presence, not runtime fallback behavior. Add a frontend unit test only
  if the app already has an established browser/fetch test harness.
- Integration should preserve the local post-base artifacts added on current
  HEAD unless the owner explicitly decides they are obsolete.

## Review Commands

```bash
git fetch origin agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify
git rev-parse origin/agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify
git merge-base HEAD origin/agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify
git diff --name-status HEAD..origin/agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify
git diff --stat HEAD..origin/agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify
git diff --check HEAD..origin/agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify
git diff a009c067fa33670b8aa2837befd0562d1e248805..origin/agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify -- frontend/src/App.jsx tests/test_factory_status.py docs/agent-work/p0-app-queue-unblock-verify-result.md
```

## Test Commands

Run in a disposable review worktree for the remote branch:

```bash
git worktree add /tmp/kolibri-p0-app-verify-review origin/agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify
cd /tmp/kolibri-p0-app-verify-review
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout
python3 -m compileall backend ops tests backend/tests
python3 -m pytest tests/test_factory_status.py
```

Cleanup:

```bash
cd -
git worktree remove /tmp/kolibri-p0-app-verify-review
```

## Safe Integration Commands For Main Executor

Dry-run the integration in a disposable worktree first:

```bash
git fetch origin agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify
git worktree add /tmp/kolibri-p0-app-verify-merge-check HEAD
cd /tmp/kolibri-p0-app-verify-merge-check
git merge --no-commit --no-ff origin/agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify
git status --short
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout
python3 -m compileall backend ops tests backend/tests
python3 -m pytest tests/test_factory_status.py
git merge --abort
cd -
git worktree remove /tmp/kolibri-p0-app-verify-merge-check
```

Only after explicit owner approval and a clean dry-run, perform the real
integration in the intended working tree:

```bash
git fetch origin agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify
git status --short --branch
git merge --no-ff origin/agent/KOL-P0-APP-QUEUE-UNBLOCK-VERIFY-20260629/app-verify
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout
python3 -m compileall backend ops tests backend/tests
python3 -m pytest tests/test_factory_status.py
```
