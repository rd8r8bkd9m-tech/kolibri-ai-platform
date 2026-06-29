# Central PR Pack - Remote Server Transfer

Task id: `KOL-REMOTE-SERVER-TASK-20260629T1617-005-PRIMARY-CENTRAL-PR-PACK`
Role slot: `autonomous_engineer`
Generated: `2026-06-29T16:17Z`
Result reference: `docs/agent-work/generated/remote-server-transfer-20260629T1617/central-pr-pack.md`

## Scope

This pack identifies the remote server transfer branches that should be pulled into the central PR, the artifact paths to retain, the recommended merge order, and the external blockers for GitHub / token-backed operations.

Baseline used for comparison:

- `origin/main`: `6d0317c52a9694448ee2c352dc196ce7a27b9487`
- local branch: `codex/kol-remote-server-task-20260629t1617-005-primary-central-pr-pack`

## Remote Commits To Pull

| Order | Purpose | Remote branch | Commit | Merge content |
| ---: | --- | --- | --- | --- |
| 1 | Main Telegram implementation and live verification gate | `origin/codex/kol-remote-server-task-20260629t1603-002b-main-telegram-implementation` | `f5ce54a97e1823bdb414e06adf0d015810486a15` | Application code, tests, generated verification artifact |
| 2 | CI / PR readiness artifact | `origin/codex/kol-remote-server-task-20260629t1603-001-primary-ci-pr` | `0f65c870941205e1e57d32add31d75839618f0f2` | Generated readiness artifacts only |
| 3 | FormulaLM remote launch artifact | `origin/codex/kol-remote-server-task-20260629t1603-004-primary-formulalm` | `b114f517b334124e5de8b4a2c805bc1e67de05dc` | Generated launch envelope, manifest, fallback message, result JSON |
| 4 | Primary result collector | `origin/codex/kol-remote-server-task-20260629t1617-004-primary-result-collector` | `9b09257a1ca9a3521b87e81f48300bf047a8ab8e` | Generated collector report, manifest, result JSON |
| 5 | Central PR pack | this branch | current task commit | Generated central PR pack artifact |

Rationale:

- Merge the Telegram implementation first because it is the only branch in this transfer set that changes runtime code and tests.
- Merge artifact-only branches after the code branch so generated readiness, FormulaLM, and collector evidence stay easy to review.
- Merge this central pack last because it summarizes all known remote refs, including the result collector branch.

## Artifacts To Retain

### Telegram implementation

- `docs/agent-work/generated/remote-server-transfer-20260629T1603/telegram-live-verification-main.md`
- `ops/telegram_gateway.py`
- `ops/telegram_rollout_gate.py`
- `tests/test_telegram_gateway.py`

Declared verification result:

- `python3 ops/telegram_rollout_gate.py --report docs/agent-work/generated/remote-server-transfer-20260629T1603/telegram-live-verification-main.md --task-id KOL-REMOTE-SERVER-TASK-20260629T1603-002B-MAIN-TELEGRAM-IMPLEMENTATION --live-telegram`
- `git diff --check`
- `git status --short`
- `test -f docs/agent-work/generated/remote-server-transfer-20260629T1603/telegram-live-verification-main.md`
- `python3 -m compileall -q ops tests`
- `python3 -m pytest -q tests/test_telegram_gateway.py tests/test_agent_host_telegram_chat.py`
- Result: `38 passed in 2.09s`
- Telegram delivery fallback: `TELEGRAM_BOT_TOKEN is not set`

### CI / PR readiness

- `docs/agent-work/generated/remote-server-transfer-20260629T1603/ci-pr-readiness-primary.md`
- `docs/agent-work/generated/remote-server-transfer-20260629T1603/agent-message-primary.md`

Declared verification result:

- `python3 -m compileall -q backend infra scripts ops tests` passed.
- Isolated pytest run passed: `60 passed, 1 warning`.
- `npm --prefix frontend run test:mobile-layout` passed.
- Local blockers: no `gh`, no `shellcheck`, no base `python` alias, no preinstalled `pytest`, local Node `v18.19.1` below frontend package requirements.

### FormulaLM remote launch

- `docs/agent-work/generated/remote-server-transfer-20260629T1603/formulalm-remote-launch-primary.md`
- `docs/agent-work/generated/remote-server-transfer-20260629T1603/agent-message-fallback.md`
- `docs/agent-work/generated/remote-server-transfer-20260629T1603/result.json`
- `docs/agent-work/generated/remote-server-transfer-20260629T1603/artifact-manifest.json`

Manifest entries from the source branch:

| Path | Bytes | SHA-256 |
| --- | ---: | --- |
| `docs/agent-work/generated/remote-server-transfer-20260629T1603/formulalm-remote-launch-primary.md` | 7852 | `f2ac6d444d48b51e4aa15162049666f2b64c3506efdd5e3abccc690a1845746d` |
| `docs/agent-work/generated/remote-server-transfer-20260629T1603/agent-message-fallback.md` | 548 | `57731c07d90518c99ab1023b4f6c4c5ac1aab92318cf42deb7424e2ac84d13fb` |
| `docs/agent-work/generated/remote-server-transfer-20260629T1603/result.json` | 1126 | `8aded5803aadb05e220d6d9576d96ce4a935c0c2466f736fe8e8e1e1871089e9` |

Declared result reference:

- `docs/agent-work/generated/remote-server-transfer-20260629T1603/result.json`

### Primary result collector

- `docs/agent-work/generated/remote-server-transfer-20260629T1617/primary-result-collector.md`
- `docs/agent-work/generated/remote-server-transfer-20260629T1617/result.json`
- `docs/agent-work/generated/remote-server-transfer-20260629T1617/artifact-manifest.json`

Declared result reference:

- `docs/agent-work/generated/remote-server-transfer-20260629T1617/result.json`

### Central PR pack

- `docs/agent-work/generated/remote-server-transfer-20260629T1617/central-pr-pack.md`

Control Plane result reference for this task:

- `docs/agent-work/generated/remote-server-transfer-20260629T1617/central-pr-pack.md`

## Merge Commands

From an up-to-date central integration branch:

```bash
git fetch --prune origin
git checkout -B central/remote-server-transfer-20260629T1617 origin/main
git merge --no-ff origin/codex/kol-remote-server-task-20260629t1603-002b-main-telegram-implementation
git merge --no-ff origin/codex/kol-remote-server-task-20260629t1603-001-primary-ci-pr
git merge --no-ff origin/codex/kol-remote-server-task-20260629t1603-004-primary-formulalm
git merge --no-ff origin/codex/kol-remote-server-task-20260629t1617-004-primary-result-collector
git merge --no-ff codex/kol-remote-server-task-20260629t1617-005-primary-central-pr-pack
```

Then run:

```bash
git diff --check origin/main..HEAD
python3 -m compileall -q backend infra scripts ops tests
python3 -m pytest -q
npm --prefix frontend install
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout
```

If local Node is still `v18.19.1`, run frontend build on Node `22` to match `.github/workflows/ci.yml`.

## Dry Merge Assessment

Dry merge-tree checks against `origin/main` completed cleanly for each candidate branch:

| Branch | Result |
| --- | --- |
| `origin/codex/kol-remote-server-task-20260629t1603-002b-main-telegram-implementation` | clean tree produced |
| `origin/codex/kol-remote-server-task-20260629t1603-001-primary-ci-pr` | clean tree produced |
| `origin/codex/kol-remote-server-task-20260629t1603-004-primary-formulalm` | clean tree produced |
| `origin/codex/kol-remote-server-task-20260629t1617-004-primary-result-collector` | clean tree produced |

Expected path overlap:

- No application-code overlap among the artifact-only branches.
- `docs/agent-work/generated/remote-server-transfer-20260629T1603/` receives independent files from the CI, Telegram, and FormulaLM branches.
- `docs/agent-work/generated/remote-server-transfer-20260629T1617/` receives collector files plus this central pack. This branch intentionally adds only `central-pr-pack.md` so it does not conflict with the collector branch's `result.json` or `artifact-manifest.json`.

## GitHub / Token Blockers

- `gh` was not available in this lease, so PR creation, PR status, and remote check monitoring must be done from an authenticated operator shell or CI runner.
- No GitHub token value is included in this artifact. If automation creates the central PR, provide a token through the normal secret channel and do not log it.
- Telegram live delivery was unavailable in the Telegram implementation branch because `TELEGRAM_BOT_TOKEN` was not set; that branch recorded a fallback artifact instead.
- FormulaLM remote benchmark execution is represented by a launch envelope. The actual benchmark should run only on an approved non-Darwin remote host with its required model/runtime secrets provided through the remote secret channel.

## Verification Commands Run For This Pack

| Command | Result | Notes |
| --- | --- | --- |
| `git fetch --prune origin` | passed | Refreshed remote refs and discovered the Telegram implementation branch. |
| `git show -s --format='%H%n%ci%n%s%n%D' <branch>` | passed | Verified all four source branch tips listed above. |
| `git diff --stat origin/main..<branch>` and `git diff --name-status origin/main..<branch>` | passed | Captured source branch file sets for the pack. |
| `git merge-tree --write-tree origin/main <branch>` | passed | Each source branch produced a clean dry merge tree against `origin/main`. |
| `test -f docs/agent-work/generated/remote-server-transfer-20260629T1617/central-pr-pack.md` | passed | Confirmed the Control Plane result reference exists. |
| `git diff --check` | passed | Generated artifact has no whitespace errors. |
| `python3 -m compileall -q backend infra scripts ops tests` | passed | Repository Python syntax check completed with no output. |
| `python3 -m pytest -q` | blocked locally | Base lease image does not have `pytest` installed: `No module named pytest`. |
| `python3 -m venv .venv-central-pr-pack && .venv-central-pr-pack/bin/python -m pip install --upgrade pip && .venv-central-pr-pack/bin/python -m pip install -r backend/requirements.txt pytest && .venv-central-pr-pack/bin/python -m pytest -q` | passed | Isolated test run completed: `60 passed, 1 warning in 4.19s`; transient `.venv-central-pr-pack` removed. |
| `npm --prefix frontend run test:mobile-layout` | passed | Frontend mobile layout guard passed. |

## Follow-up Tasks

- Create the central PR from the ordered integration branch using an authenticated GitHub workflow or operator shell.
- Let GitHub Actions run on Node `22` before treating frontend build status as final.
- Run FormulaLM benchmark execution from the approved remote host and attach sanitized metrics/log artifacts to the same transfer directory.
