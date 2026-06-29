# CI / PR Readiness - Primary

Task id: `KOL-REMOTE-SERVER-TASK-20260629T1603-001-PRIMARY-CI-PR`
Role slot: `autonomous_engineer`
Generated: `2026-06-29T16:03Z`
Result reference: `docs/agent-work/generated/remote-server-transfer-20260629T1603/ci-pr-readiness-primary.md`

## Files to stage

Stage only the generated readiness artifacts from this role:

```bash
git add docs/agent-work/generated/remote-server-transfer-20260629T1603/ci-pr-readiness-primary.md \
        docs/agent-work/generated/remote-server-transfer-20260629T1603/agent-message-primary.md
```

No source files were changed by this readiness pass.

## Verification commands run

| Command | Result | Notes |
| --- | --- | --- |
| `git status --short` | passed | Worktree was clean before artifact creation. |
| `python -m compileall -q backend infra scripts ops tests` | blocked locally | `python` executable is absent in this lease image. CI `actions/setup-python` provides `python`. |
| `python3 -m compileall -q backend infra scripts ops tests` | passed | Syntax compile completed with no output. |
| `python3 -m pytest -q` | blocked locally | `pytest` was not installed in the base lease image. |
| `python3 -m venv .venv-ci && .venv-ci/bin/python -m pip install --upgrade pip && .venv-ci/bin/python -m pip install -r backend/requirements.txt pytest && .venv-ci/bin/python -m pytest -q` | passed | `60 passed, 1 warning in 4.38s`. Transient `.venv-ci` removed after verification. |
| `command -v shellcheck && shellcheck scripts/deploy.sh scripts/training/run_pipeline.sh ops/install-telegram-secret.sh ops/kolibri-dispatch` | blocked locally | `shellcheck` is unavailable in this lease image. |
| `command -v gh && gh pr status` | blocked locally | `gh` is unavailable in this lease image. |
| `npm --prefix frontend install --no-package-lock` | passed with warnings | Installed transient `node_modules`; warnings are from local Node `v18.19.1` versus packages requiring Node 20/22. Transient `node_modules` removed after verification. |
| `npm --prefix frontend run build` | blocked locally | Vite requires Node `20.19+` or `22.12+`; lease has Node `v18.19.1`. CI uses Node `22`. |
| `npm --prefix frontend run lint` | blocked by repo config | ESLint 10 could not find `eslint.config.(js\|mjs\|cjs)`. CI currently skips lint when no ESLint config is tracked. |
| `npm --prefix frontend run test:mobile-layout` | passed | `mobile layout guard passed`. |

## Blockers

### Local lease blockers

- `gh` is not installed, so PR status/check inspection could not be performed locally.
- `shellcheck` is not installed, so shell script lint could not be performed locally.
- Base image has no `python` alias and no preinstalled `pytest`; Python verification required `python3` plus an isolated virtualenv.
- Base image Node is `v18.19.1`; frontend build dependencies require Node 20/22. GitHub CI config uses Node `22`, so this is expected to be a local-only blocker.

### Repository / CI-readiness blockers

- `npm --prefix frontend run lint` fails manually because no flat ESLint config is tracked. Current CI logic intentionally skips frontend lint when no config file exists, even though the lint script is present.
- `shellcheck` is not part of the current CI workflow. If shell lint is required as a merge gate, add a CI install/step or provide a factory image with `shellcheck`.
- `gh pr status` could not be used from this lease. PR creation/check monitoring should happen from a runner or operator shell that has GitHub CLI/auth available.

## PR order

1. Stage the two generated artifact files listed above.
2. Run `git diff --check`.
3. Commit with a task-scoped message, for example:

   ```bash
   git commit -m "docs: add primary CI PR readiness artifact"
   ```

4. Push branch `codex/kol-remote-server-task-20260629t1603-001-primary-ci-pr`.
5. Open a draft PR against the configured base branch.
6. Let GitHub Actions run the workflow in `.github/workflows/ci.yml`.
7. If CI frontend build fails, reproduce with Node `22` first because local Node `18` is below the package engine requirement.
8. If CI production secret path guard fails, inspect only the changed file paths; do not print secret values.
9. Mark the PR ready after CI passes or after documenting any remaining external blockers in the PR body.

## Telegram fallback

No Telegram delivery channel was available in this lease. Fallback agent-message/report was written to:

`docs/agent-work/generated/remote-server-transfer-20260629T1603/agent-message-primary.md`

