# P0 GitHub Release Train Queue Audit

Task: `P0_AUTOPILOT_EXTRA_36_GITHUB_RELEASE_TRAIN_QUEUE_2026_07_02`
Role slot: `autonomous_engineer`
Agent name: `Codex autonomous_engineer`
Node: `kolibri`
Execution time: `2026-07-02T02:55Z`
Repository: `rd8r8bkd9m-tech/kolibri-ai-platform`
Local branch: `agent/P0_AUTOPILOT_EXTRA_36_GITHUB_RELEASE_TRAIN_QUEUE_2026_07_02/generic`

## Status

- Remote execution happened on the assigned server-side mesh worker: `hostname=kolibri`, `whoami=root`, workspace under `/var/lib/kolibri-agent/logical-workers/.../repo`.
- Local product code was not modified. This audit added only this artifact file under `artifacts/`.
- No merges, pushes, force-pushes, deploys, restarts, destructive git commands, or pushes to `main` were performed.
- No secrets were printed. GitHub metadata was read through the GitHub connector and read-only git commands.
- `gh` is not installed on this worker; GitHub REST without auth returned `404`, so CI log inspection via `gh run view` was unavailable.

## Evidence Commands

- `hostname && whoami && date -u +%Y-%m-%dT%H:%M:%SZ`
- `git status --short --branch`
- `git remote -v`
- `git ls-remote origin 'refs/pull/*/head'`
- GitHub connector: list open PRs, get PR metadata, get commit combined status, list changed filenames.

## CI Classification

The GitHub connector `get_commit_combined_status` returned an empty status list for the current July 2 open heads checked:

- PR #105 `dd86dd8`
- PR #106 `2dd7741`
- PR #107 `762d1b9`
- PR #108 `8ea1aa4`
- PR #109 `b9f761b`
- PR #110 `9253e6b`
- PR #111 `f3a9792`
- PR #112 `90c7160`
- PR #113 `26fe979`

Classification: **CI missing / not attached**, not green. Do not mark ready or merge until a fresh GitHub Actions run or equivalent release-gate evidence is attached to each final head.

Older heads checked through combined status also returned empty status lists for #94, #93, #90, #87, and #86. PR bodies contain historical local/server verification, but current release order must treat GitHub status as absent unless a separate Actions check is confirmed.

## Hot Lane Merge Order

These PRs are based on current `main` `f7ac32c`, are connector-reported `mergeable=true`, and are the only reasonable current hot lane. They are all draft and currently CI-missing.

1. **PR #109 - factory status proxy 504 canary**
   - Files: `backend/factory_status.py`, `backend/tests/test_factory_status_fast_health.py`, run artifacts.
   - Order reason: narrowest runtime surface; independent from `ops/factory_control.py` queue.
   - Required before merge: mark ready only after focused backend status tests and fresh CI.

2. **PR #107 - release queue accelerator**
   - Files: dispatcher docs, `ops/release_queue_accelerator.py`, `tests/test_release_queue_accelerator.py`.
   - Order reason: self-contained queue tooling; does not overlap `ops/factory_control.py`.
   - Required before merge: fresh CI and owner review of queue policy.

3. **PR #106 - runner contract steward fallback**
   - Files: `docs/agent/AGENT_RUNNER_CONTRACT.md`, `ops/agent_host.py`, runner tests.
   - Order reason: prepares runner contract before overlapping runtime-control PRs.
   - Required before merge: fresh runner-contract test suite and no overlap regression with already-merged #83/#96.

4. **PR #112 - runner timebox and max-inflight contract**
   - Files: `ops/agent_host.py`, `ops/factory_control.py`, runner/runtime tests.
   - Order reason: depends conceptually on runner contract baseline; starts the `ops/factory_control.py` overlap queue.
   - Required before merge: rebase after #106 if merged; fresh focused tests.

5. **PR #110 - primary node heartbeat read-only path**
   - Files: `ops/factory_control.py`, `tests/test_fabric_control.py`, run artifacts.
   - Order reason: small `factory_control` change after runner/timebox baseline.
   - Required before merge: rebase after #112; focused fabric-control tests.

6. **PR #105 - Fabric route freshness gate**
   - Files: `ops/factory_control.py`, `tests/test_prompt3_fabric_api_surface.py`, run artifact.
   - Order reason: related to route correctness; should follow heartbeat freshness/read-only semantics.
   - Required before merge: rebase after #110; rerun prompt3/fabric API tests.

7. **PR #108 - fleet online freshness accelerator**
   - Files: `ops/factory_control.py`, `tests/test_factory_runtime.py`, run artifacts.
   - Order reason: broader freshness behavior, likely overlapping #105/#110.
   - Required before merge: rebase after #105; runtime queue/freshness tests.

8. **PR #111 - queue lease debt audit and requeue policy**
   - Files: `ops/factory_control.py`, `ops/kolibri-dispatch`, `tests/test_factory_runtime.py`, run artifacts.
   - Order reason: queue mutation policy should land after route/freshness behavior is stable.
   - Required before merge: rebase after #108; dispatch and factory runtime tests.

9. **PR #113 - factory-control runtime import path repair**
   - Files: `ops/factory_control.py`, systemd unit, preflight script, import-path test, run artifacts.
   - Order reason: includes deploy/service preflight surface; merge last among current control-plane runtime PRs.
   - Required before merge: rebase after all preceding `factory_control` PRs; run preflight script and focused import-path tests.

## Repair Lane

- **PR #90 - Telegram Mini App owner auth verifier contract**
  - Mergeable draft, but base is stale and it changes `backend/main.py`, `backend/telegram_miniapp_auth.py`, backend tests, and root test path.
  - Blocker: body records system Python missing `fastapi`; venv tests passed historically.
  - Action: rebase on current `main`, remove root-level artifact clutter if not required, rerun Telegram Mini App auth tests in dependency-satisfied environment, then attach fresh CI.

- **PR #81 - live Telegram dialog without TGCHAT tasks**
  - Non-mergeable draft; changes Telegram gateway, mesh bridge, agent host.
  - Action: split or rebase after #89 merged state and current Telegram receiver policy. Do not merge until single-receiver migration constraints are reconfirmed.

- **PR #61 - Telegram miniapp and owner director bot**
  - Non-mergeable ready PR; stale relative to merged Telegram work.
  - Action: close or supersede after extracting any still-missing behavior into a new small PR.

- **PR #26 - client SDK foundation**
  - Open, old, likely stale frontend SDK layer.
  - Action: rebase and run current frontend build/tests on Node 20.19+ or split SDK-only contract from UI wiring.

- **PR #25 - temporary subagent exception**
  - Non-mergeable ready PR.
  - Action: close as obsolete if remote runner/agent-host policies are now represented by merged #83/#96 and current queue PRs.

## Split / Archive Lane

- **PR #46 - Factory autonomy, PWA billing, remote FormulaLM**
  - Non-mergeable draft, 40 commits, 262 files, about 49k additions.
  - Classification: split required. Do not merge as a single PR.
  - Split order: factory runtime contracts, billing API scaffold, frontend PWA shell changes, deterministic estimate fixtures, FormulaLM benchmark harness/artifacts.

- **PR #74 - FormulaLM R&D preflight**
  - Mergeable draft against PR #46 branch, not `main`.
  - Classification: depends on split of #46 or must be retargeted as docs/benchmark-only PR.

- **PR #65 - GoMesh rollout verification runbook**
  - Mergeable draft against old launch branch, docs/tooling heavy.
  - Classification: retarget to `main` as docs-only/runbook-only after secret scan; no rollout apply.

- **PR #60 - home result capture**
  - Mergeable ready PR against `codex/factory-autonomy-pwa-billing`, not `main`.
  - Classification: archive or retarget as a tiny docs-only evidence PR if still valuable.

- **PRs #1-#8 and #24**
  - Historical stacked branches on `codex/mimo-orchestration`, `codex/public-proxy-chat-contract`, `factory/KOL-LAUNCH...`, and `codex/kolibri-vertical-slice`.
  - Classification: not part of current main release train. Close/archive after verifying their substance is either merged, superseded, or deliberately re-cut.

## Docs-Only Review Lane

- **PR #84 - Kolibri Superfactory master canvas**
  - Mergeable draft, docs-only, stale base.
  - Action: rebase on current `main`, run `git diff --check`, then merge only if owner wants the canvas in main.

- **PR #86 - GitHub operating system governance package**
  - Draft, docs/templates/governance files.
  - Risk: `.github/CODEOWNERS`, issue templates, PR template, `SECURITY.md`, and `CONTRIBUTING.md` alter repo behavior.
  - Action: owner review required; merge after hot lane or split `.github` behavior-changing files from docs.

- **PR #87 - Kwork revenue manager package**
  - Draft, docs/business and portfolio assets.
  - Action: owner commercial review required; safe after hot lane if no product release urgency.

- **PR #93 and #94 - PR85 review artifacts**
  - Draft artifact PRs; PR #85 is already merged.
  - Action: close or merge only if artifact preservation is required. They should not block runtime release.

## Blockers

- No `gh` binary on this worker; Actions log inspection is blocked.
- Combined status returned no statuses for checked open heads; CI must be treated as absent.
- Most July 2 queue PRs overlap on `ops/factory_control.py`; merge order must be serial with rebase and focused tests after each merge.
- Several older PRs are non-mergeable or based on non-main stacked branches.
- PR #46 is too large and mixed for a responsible merge.
- Telegram PRs must respect the single canonical receiver constraint before any live deployment or receiver enablement.

## Next Exact Task

Dispatch `P0_PR109_FACTORY_STATUS_PROXY_504_READY_GATE_2026_07_02`:

1. Rebase PR #109 on current `main`.
2. Run `python3 -m pytest -q backend/tests/test_factory_status_fast_health.py tests/test_factory_status.py`.
3. Run `python3 -m compileall -q backend ops tests`.
4. Trigger/confirm fresh GitHub CI on PR #109 head.
5. If green, ask owner to mark PR #109 ready and merge first.

## Owner Summary (Russian)

Очередь нельзя сливать пачкой. Новые PR #105-#113 технически mergeable и стоят на свежем `main`, но все draft и без прикрепленных GitHub status checks, поэтому они не green. Самый безопасный первый шаг: PR #109, потому что он узкий и не конфликтует с большой очередью `ops/factory_control.py`.

После #109 нужно идти маленькими слоями: #107, #106, затем строго по одному PR с `ops/factory_control.py`: #112, #110, #105, #108, #111, #113. После каждого merge нужен rebase следующего PR и focused tests.

Старые PR #46, #61, #81, #90 и похожие нельзя тащить в main напрямую: там stale base, non-mergeable состояние, Telegram single-receiver риск или слишком широкий scope. PR #46 нужно резать на отдельные PR, иначе main снова начнет стареть и конфликтовать.
