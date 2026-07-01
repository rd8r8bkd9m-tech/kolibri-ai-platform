# Factory Status

Snapshot time:
- 2026-07-01T03:28:51Z

Latest update:
- 2026-07-01T04:22:48Z: PR #89 Telegram Superfactory branch is now at
  `2b7cec1560276c31eb0d63d6b1a386c7ea00cce3`.
- Server task `P0_PR89_TELEGRAM_SUPERFACTORY_CANONICAL_ARTIFACTS_2026_07_01`
  pushed docs-only commit `041ea9ca5e27f6826450ff20b340c018b474eeed`, but
  Control Plane still marked it failed because the generic runner missed exact
  `PLAN.md/ACTIONS.md/TESTS.md/RESULT.md/NEXT.md` artifact names.
- Mac performed an explicit thin-client artifact relay only for those five
  missing run docs; no product code was changed by the relay.
- GitHub Actions `Kolibri CI` run `28493219207` for `2b7cec15` succeeded.
- PR #89 remains draft and live deployment remains blocked until a single
  canonical Telegram update receiver is proven.

Mac executor:
- Hostname: `MacBook-Air-Vladislav.local`
- Kernel: `Darwin`
- Role: thin intelligent dispatcher only.

Control Plane:
- Default URL: `http://10.99.0.2:9101`
- Direct Mac health check: timeout after 5 seconds.
- Server-side check through `kolibri-primary-codex` to
  `http://10.99.0.2:9101/health`: `status=ok`, `redis=PONG`.
- `kolibri-primary-codex` local `127.0.0.1:9101` check failed; the active
  listener observed on that node is `10.99.0.10:9101`.
- Status: direct Mac route unavailable; fallback route through
  `kolibri-primary-codex` to mesh Control Plane is available.

Fabric law:
- API-first control is the primary management path.
- SSH is bootstrap, emergency recovery and diagnostics only.
- Agent responses must not dead-end at `server unavailable`; they must return a
  structured status with reason, fallback nodes, repair task and next action.
- Full owner control through API must be authenticated, authorized, scoped,
  logged, token-bound or signed, and protected from secret leakage.

Emergency SSH layer:
- Mac emergency-login topology probe checked 20 server aliases:
  `ok=20`, `fail=0`, `total=20`.
- This is a diagnostic/bootstrap layer only; normal control must move through
  Fabric API and fallback routing.

Submitted tasks:
- `P0_AGENT_HOST_GENERIC_RUNNER_CONTRACT_HARDENING_2026_06_30`: accepted by
  Control Plane at `2026-06-30T21:50:31Z`, state `queued`.
- Same task leased by `primary-candidate:agent-host-primary`, state `running`,
  heartbeat observed at `2026-06-30T21:51:23Z`.
- Latest observed heartbeat: `2026-06-30T21:54:24Z`; result fields are still
  empty.
- Latest exact task query observed heartbeat `2026-06-30T21:57:54Z`, state
  `running`, lease owner `primary-candidate:agent-host-primary`, result fields
  still empty.
- `P0_API_FIRST_FULL_CONTROL_FABRIC_2026_07_01`: accepted by Control Plane at
  `2026-06-30T23:15:13Z`; leased by
  `primary-candidate:agent-host-primary`; final Control Plane state `failed`
  at `2026-06-30T23:21:44Z` because required `docs/superfactory/*` files were
  missing. Artifact contains useful uncommitted implementation with remote test
  report `65 passed, 1 warning`; finalization task is required.
- `P0_API_FIRST_FULL_CONTROL_FABRIC_FINALIZE_2026_07_01`: accepted by Control
  Plane at `2026-06-30T23:26:24Z`; leased by
  `primary-candidate:agent-host-primary`; final Control Plane state `failed`
  because exact verifier filenames were missing, but it created draft PR #85
  and pushed branch head `44d7b9a`.
- `P0_API_FIRST_FULL_CONTROL_FABRIC_CONTRACT_ALIGN_2026_07_01`: accepted by
  Control Plane at `2026-06-30T23:38:28Z`; leased by
  `primary-candidate:agent-host-primary`; final Control Plane state `failed`
  because exact verifier filenames were still missing. Artifact contains useful
  docs-only commit evidence and remote tests `65 passed, 1 warning`.
- PR #85 was then synchronized through a thin-client relay of the server commit.
  GitHub source of truth now has branch
  `p0/api-first-full-control-fabric-2026-07-01` at
  `9690361f02addeff37771c52fd37878aef455e13`.
- GitHub API confirmed exact required files exist, including
  `docs/superfactory/API_FIRST_CONTROL_FABRIC.md` and
  `docs/agent/runs/2026-07-01-p0-api-first-full-control-fabric/RESULT.md`.
- GitHub Actions `Kolibri CI` run `28483527200` completed with conclusion
  `success`.
- `P0_REPAIR_QJNS_UIAP_DISK_2026_07_01`: Control Plane task state is `failed`
  because final verifier required missing `docs/agent/runs/.../RESULT.md`.
  Artifact stdout shows effective repair succeeded and current Control Plane
  cards confirm free disk on both nodes.
- `P0_AGENT_HOST_GENERIC_RUNNER_CONTRACT_HARDENING_2026_07_01`: submitted at
  `2026-07-01T02:12:34Z`; leased by `primary-candidate:agent-host-primary`.
  Final Control Plane state is `failed` because the wrapper required
  `docs/agent/runs/2026-07-01-p0-agent-host-runner-contract-hardening-finalize/PLAN.md`,
  while the remote agent preserved and updated the existing
  `2026-06-30` run artifact set.
- Despite the wrapper failure, remote agent `Алексей` finalized PR #83 on the
  existing source branch `p0/agent-host-runner-contract-hardening-2026-06-30`.
  GitHub `refs/pull/83/head` and the branch both point to
  `5b5bfc17f2efc49974173ebe6287bf1501c44bc2`.
- PR #83 remote artifact reports: runner contract tests `13 passed`, Agent
  Host tests `19 passed`, factory runtime tests `4 passed`, full suite
  `73 passed, 1 warning`, plus `py_compile`, JSON validation,
  `git diff --check` and remote branch verification passed.
- GitHub Actions `Kolibri CI` run `28488999139` for PR #83 completed with
  conclusion `success`.
- `P0_PR83_MERGE_READINESS_AND_RUNNER_PUBLISH_GATE_AUDIT_2026_07_01`:
  submitted at `2026-07-01T02:27:40Z` through the fallback route
  `Mac -> kolibri-primary-codex -> Control Plane`; leased by
  `primary-candidate:agent-host-primary`; final Control Plane state `failed`
  at `2026-07-01T02:35:40Z`. Artifact root:
  `/var/lib/kolibri-agent/artifacts/P0_PR83_MERGE_READINESS_AND_RUNNER_PUBLISH_GATE_AUDIT_2026_07_01/P0_PR83_MERGE_READINESS_AND_RUNNER_PUBLISH_GATE_AUDIT_2026_07_01-attempt-1/`.
- The wrapper failed because it expected
  `docs/agent/runs/2026-07-01-p0-pr83-merge-readiness-and-runner-publish-gate-audit/PLAN.md`.
  Remote agent `Сергей` created audit artifacts under
  `docs/agent/runs/2026-07-01-p0-pr83-merge-readiness-runner-publish-gate-audit/`
  and did not create all five canonical docs. This is another artifact path
  contract mismatch, not evidence that the code change failed.
- Useful remote result: `Сергей` pushed PR #83 branch to
  `8b156572217cc646fc0e0fb779dbb1ecc37f1561`, classified the updated head as
  `merge_ready`, and explicitly answered that PR #83 already blocked false
  `completed` but did not previously gate GitHub publishing before verifier
  artifacts. The new head adds that publish-after-verification gate.
- Remote tests reported: `python3 -m py_compile ops/agent_host.py` passed;
  runner contract tests `15 passed`; Agent Host glob tests `21 passed`; full
  suite `75 passed, 1 warning`.
- GitHub connector confirms PR #83 is open, draft, mergeable, and now points to
  `8b156572217cc646fc0e0fb779dbb1ecc37f1561`.
- GitHub Actions `Kolibri CI` run `28489561399` for PR #83 head
  `8b156572217cc646fc0e0fb779dbb1ecc37f1561` completed with conclusion
  `success`.
- `P0_PR83_SCOPE_CLEANUP_REMOVE_SUPERFACTORY_OVERLAP_2026_07_01`: submitted
  at `2026-07-01T02:40:15Z` through the fallback route
  `Mac -> kolibri-primary-codex -> Control Plane`; final Control Plane state
  `failed` at `2026-07-01T02:44:50Z` because the wrapper expected
  `docs/agent/runs/2026-07-01-p0-pr83-scope-cleanup-remove-superfactory-overlap/NEXT.md`.
  Artifact root:
  `/var/lib/kolibri-agent/artifacts/P0_PR83_SCOPE_CLEANUP_REMOVE_SUPERFACTORY_OVERLAP_2026_07_01/P0_PR83_SCOPE_CLEANUP_REMOVE_SUPERFACTORY_OVERLAP_2026_07_01-attempt-1/`.
- Useful remote result: PR #83 branch now points to
  `c837e93ee3bf9da3c07b806ebfc003f52b9ad8d5`; unrelated
  `docs/superfactory/00_README.md`, `docs/superfactory/20_ROADMAP.md`, and
  `docs/superfactory/TASKS.md` were removed from the PR diff; focused runner
  contract test reported `15 passed`; GitHub Actions `Kolibri CI` run
  `28489876130` completed with conclusion `success`.
- PR #83 body was refreshed through the GitHub connector at
  `2026-07-01T02:46:43Z` to record the current head, publish gate, scope
  cleanup, remote validation, GitHub Actions success, and the remaining
  canonical artifact contract follow-up. The PR remains draft and unmerged.
- `P0_CANONICAL_RUN_ARTIFACT_CONTRACT_AND_ALIASES_2026_07_01`: submitted at
  `2026-07-01T02:50:44Z` through the fallback route
  `Mac -> kolibri-primary-codex -> Control Plane`; leased by
  `primary-candidate:agent-host-primary`; final Control Plane state `failed`
  at `2026-07-01T02:58:19Z`. Artifact root:
  `/var/lib/kolibri-agent/artifacts/P0_CANONICAL_RUN_ARTIFACT_CONTRACT_AND_ALIASES_2026_07_01/P0_CANONICAL_RUN_ARTIFACT_CONTRACT_AND_ALIASES_2026_07_01-attempt-1/`.
  Useful remote result: remote agent `Дмитрий` implemented/tested canonical
  `PLAN/ACTIONS/TESTS/RESULT/NEXT` artifact behavior, created the exact five
  run docs, and pushed PR #83 branch to
  `8951a9feb4a44b8dd87a762d0da199257de1dae0`.
- The latest wrapper failure is now narrower: the final verifier command used
  `python3 -m pytest tests/test_agent_host.py tests/test_agent_host_runner_contract.py -q`,
  but `tests/test_agent_host.py` is not present in this branch. Useful remote
  validation passed: canonical runner contract `20 passed`, relevant Agent
  Host suite `26 passed`, `compileall` passed, `git diff --check` passed, and
  forbidden `docs/superfactory/*` files were not touched. GitHub Actions
  `Kolibri CI` run `28490349624` for `8951a9f` completed with conclusion
  `success`.
- Current P0 runner hardening estimate: about 96% done. Remaining work is to
  dispatch a micro cleanup for stale verifier-command assumptions and then
  convert PR #83 from draft when the owner approves merge/release policy.
- `P0_PR83_VERIFIER_COMMAND_CLEANUP_PROOF_2026_07_01`: submitted at
  `2026-07-01T03:19:16Z` through the fallback route
  `Mac -> kolibri-primary-codex -> Control Plane`; leased by
  `primary-candidate:agent-host-primary`. Control Plane state is now
  `completed`, with result artifact
  `/var/lib/kolibri-agent/artifacts/P0_PR83_VERIFIER_COMMAND_CLEANUP_PROOF_2026_07_01/P0_PR83_VERIFIER_COMMAND_CLEANUP_PROOF_2026_07_01-attempt-1/result.json`.
- Useful remote result: result JSON reports `status=completed`; PR #83 branch
  was pushed normally from `8951a9feb4a44b8dd87a762d0da199257de1dae0` to
  `9bebf6cdba32a6886b6343f3701add3e85d18e41`; exactly five canonical proof
  artifacts were created under
  `docs/agent/runs/2026-07-01-p0-pr83-verifier-command-cleanup-proof/`; no
  product code changed.
- Verification for the PR #83 proof passed remotely: focused runner contract
  `20 passed`; relevant Agent Host suite `26 passed`; `python3 -m py_compile
  ops/agent_host.py`; `git diff --check`; Superfactory overlap guard returned
  no paths. GitHub Actions `Kolibri CI` run `28491266003` completed with
  conclusion `success`.
- The dispatcher used the supported `/v1/tasks/<task_id>/annotate` endpoint to
  add PR #83 URL to the result. This created review task
  `P0_PR83_VERIFIER_COMMAND_CLEANUP_PROOF_2026_07_01-REVIEW`; the review task
  is currently `queued` and carries `error=lease expired before task
  completion`, so it needs normal review-agent pickup or a small review lease
  repair if it does not recover.

Node snapshot through Control Plane:
- Observed node cards: 42.
- Canonical nodes: 20.
- Fresh canonical nodes: 19.
- Fresh canonical generic implementation nodes: 7.
- Healthy owner-relevant execution nodes include `home`, `home-live`, `main`,
  `mesh-9fts`, `primary-candidate`, and mesh `agent-01..03` cards with
  implementation capability.
- `qjns`: online; current free disk observed `10970157056` bytes.
- `uiap`: online; current free disk observed `27758845952` bytes; RAM is tight
  (`MemAvailable` observed around `126788 kB`), so use for research/RAG only
  until resource pressure is reviewed.
- `main`: online; current free disk observed `7614488576` bytes; known
  Codex/MIMO runner auth is broken from prior task attempts.
- `primary-candidate`: online; latest exact PR #83 verifier cleanup proof is
  `completed` on `primary-candidate:agent-host-primary`; the associated review
  task is queued. PR #83 is currently CI-green and GitHub reports it mergeable
  at head
  `9bebf6cdba32a6886b6343f3701add3e85d18e41`.
- Many mesh cards are degraded/stale or metadata-only; they need inventory
  before broad execution.
- Aggregate `/v1/tasks` response showed 200 queued tasks while the direct P0
  endpoint showed `running`; treat aggregate queue status as stale/limited and
  use the direct task endpoint for P0 truth.

Known constraints:
- Do not run product implementation on Mac.
- Do not run heavy tests on Mac.
- Do not claim remote execution without task status/artifacts.
- Do not expose secrets.
- Use API-first paths for normal control. Use SSH only for bootstrap,
  emergency recovery and diagnostics.

Current blockers:
- Agent Host generic runner/verifier contract was narrowed substantially by PR
  #83 and the latest proof is CI-green. The source task is now completed, but
  the generated review task is queued with a stale lease-expired marker and
  needs review-agent pickup or a focused review lease repair.
- Agent Host generic runner/verifier contract was historically too weak:
  useful work could be pushed while task state still became `failed` due exact
  artifact filename mismatches. PR #83 now contains the hardening/proof path;
  keep it draft until the owner approves merge/release policy.
- P0 runner hardening is now a concrete example of the same issue: PR #83 is
  finalized on GitHub, but the Control Plane wrapper state is failed because
  the artifact contract allowed ambiguity between preserving the existing run
  folder and requiring a new timestamped folder.
- The PR #83 publish-gate follow-up fixed the more serious branch-publication
  gap, but it also repeated the artifact-name mismatch. The next runner task
  should make run artifact aliases/canonical names machine-enforced before
  further broad factory prompts.
- Server shell GitHub write path on `primary-candidate` is not reliable:
  GitHub SSH port 22 timed out and SSH over port 443 authenticated with a
  read-only key. Mac had to relay the server commit to GitHub over HTTPS.
- `main` still has Codex/MIMO runner auth failures from prior attempts.

Known fleet notes from current owner context:
- Owner-facing server set is 20 servers; latest emergency SSH probe reached
  all 20.
- Control Plane currently exposes 42 node cards because it includes mesh,
  stale and metadata cards in addition to the owner-facing server set.
- `qjns` and `uiap` disk pressure was effectively repaired, but retention
  cleanup and GitHub auth validation are still follow-up tasks.
