# Factory Status

Snapshot time:
- 2026-07-01T06:38:29Z

Latest update:
- 2026-07-01T06:38:29Z:
  `P0_TELEGRAM_MINIAPP_OWNER_AUTH_CONTRACT_2026_07_01` is running on
  `primary-candidate:agent-host-primary`. Control Plane accepted it at
  `2026-07-01T06:38:12Z` and created attempt
  `P0_TELEGRAM_MINIAPP_OWNER_AUTH_CONTRACT_2026_07_01-attempt-1`. Scope is
  deliberately narrow: backend `initData` verification, short-lived session /
  role response, redaction-safe behavior and tests only. No frontend, ops, live
  Telegram receiver/webhook/menu/service mutation, payments, Guest Mode,
  Business mode or Bot-to-Bot behavior is allowed.
- 2026-07-01T06:31:00Z:
  `P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01`
  finished as `failed` in Control Plane, and that status is correct. The
  remote agent produced useful docs, but wrote them to non-contract paths
  (`docs/telegram-*` and `artifacts/...`) while the envelope required
  `docs/product/telegram-command-center/2026-07-01/*` and exact run artifacts.
  The dispatcher imported the useful remote docs as a deterministic
  thin-client relay under the exact paths. No product code, runtime service,
  backend/frontend implementation, tests, GitHub Actions or live Telegram state
  was changed by the relay.
- 2026-07-01T06:26:31Z:
  `P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01`
  is running on `primary-candidate:agent-host-primary`. Control Plane accepted
  it at `2026-07-01T06:25:08Z`, assigned attempt
  `P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01-attempt-1`,
  and created artifacts under
  `/var/lib/kolibri-agent/artifacts/P0_TELEGRAM_FACTORY_COMMAND_CENTER_SPEC_AND_RUNTIME_GAP_AUDIT_2026_07_01/`.
  This is docs/audit-only: no product code, live Telegram mutation, service
  restart, `getUpdates`, webhook change, token rotation or deployment is
  allowed.
- 2026-07-01T06:12:43Z:
  `P0_AGENT_HOST_REVIEW_CLONE_AND_CONSTRAINT_ENFORCEMENT_2026_07_01`
  completed on `primary-candidate:agent-host-primary`. PR #83 branch
  `p0/agent-host-runner-contract-hardening-2026-06-30` was fast-forwarded to
  `23e8e43fdff8eeda192df2349215e17882983d58`; GitHub Actions `Kolibri CI`
  run `28497411550` completed with conclusion `success`. Remote verification:
  focused runner contract suite `25 passed`, relevant Agent Host suite
  `31 passed`, `py_compile`, `git diff --check`, exact run artifacts and
  Superfactory-overlap guard passed. Key contract change: read-only/no-push
  envelopes lose `git_push`/`full_autonomy`, no-push publish paths are gated,
  missing exact artifacts cannot complete, and review clone/auth failures write
  `result.json` with actionable `review_clone_auth_failed` classification.
- 2026-07-01T06:06:17Z:
  `P0_AGENT_HOST_REVIEW_CLONE_AND_CONSTRAINT_ENFORCEMENT_2026_07_01` is
  running on `primary-candidate:agent-host-primary` against PR #83 branch
  `p0/agent-host-runner-contract-hardening-2026-06-30`. It was accepted by
  Control Plane at `2026-07-01T05:59:23Z`; latest direct task heartbeat is
  `2026-07-01T06:06:06Z`. This task targets the current P0 factory law gap:
  read-only/no-push envelopes still receiving `git_push`, no-push tasks
  publishing central branches, exact artifact aliases collapsing useful results
  into `failed`, and review clone failures pointing at missing result files.
- 2026-07-01T05:53:39Z:
  `P0_PR89_DELETEWEBHOOK_SAFETY_GATE_2026_07_01` has a useful GitHub result
  but failed its Control Plane wrapper on an exact artifact alias check. Remote
  agent pushed PR #89 branch to `1c341ebb83a6a4eb66ea8ce5d739a21d2d4d9be0`
  with the Telegram delivery-state safety gate; thin-client relay then added
  exact `PLAN/ACTIONS/TESTS/RESULT/NEXT` artifact aliases and pushed PR #89 to
  `da70104545c4d213807b22f01b4f06f86ac2204e`. GitHub Actions `Kolibri CI`
  run `28496630947` completed with conclusion `success`. PR #89 remains draft:
  do not live-roll out until owner approves a maintenance window and smoke
  checks.
- 2026-07-01T05:46:43Z:
  `P0_PR89_DELETEWEBHOOK_SAFETY_GATE_2026_07_01` is running on
  `primary-candidate:agent-host-primary` against branch
  `p0/telegram-superfactory-bot-miniapp-2026-07-01`. It was submitted through
  the Control Plane at `2026-07-01T05:37:12Z`; latest heartbeat is fresh and
  there is no result artifact yet. This task is allowed to update only PR #89
  branch and is forbidden from live Telegram API calls, service mutation, token
  rotation, pending update deletion, second receiver enablement, push to main or
  force push.
- 2026-07-01T05:32:22Z:
  `P0_TELEGRAM_PR89_MAIN_RECEIVER_CUTOVER_PLAN_2026_07_01` completed on
  `primary-candidate:agent-host-primary`. Five exact artifacts were created
  under
  `docs/agent/runs/2026-07-01-p0-telegram-pr89-main-receiver-cutover-plan/`
  and central branch
  `p0/telegram-pr89-main-receiver-cutover-plan-2026-07-01` exists at
  `437613ebdffd20a730be4592fd08de5944637ead`. Result: PR #89 must not roll
  out live unchanged. The plan requires preserving exactly one receiver on
  `main` and moving `deleteWebhook(drop_pending_updates=False)` behind an
  explicit owner-approved migration gate before any live rollout. Contract
  warning: this read-only/no-push task still received `full_autonomy`/`git_push`
  and pushed a central branch, so runner hardening remains P0.
- 2026-07-01T05:24:00Z: Prepared
  `P0_TELEGRAM_PR89_MAIN_RECEIVER_CUTOVER_PLAN_2026_07_01` for a healthy
  review node. The live receiver is now confirmed on `main`; the next step is a
  read-only rollout/cutover plan, not a second receiver.
- 2026-07-01T05:19:56Z:
  `P0_TELEGRAM_MAIN_RECEIVER_TOKEN_LINEAGE_AND_IDENTITY_2026_07_01` failed in
  Control Plane because the `main` Codex runner token is expired/reused. A
  remote SSH diagnostic fallback on `kolibri-main` confirmed the live receiver
  token identity: `getMe` returned username `kolibriai_bot`; service is
  active/running; state file offset exists; webhook is empty and pending updates
  are `0`.
- 2026-07-01T05:18:00Z: Prepared
  `P0_TELEGRAM_MAIN_RECEIVER_TOKEN_LINEAGE_AND_IDENTITY_2026_07_01` for
  `main`. This is the next safe step after fleet discovery found an active
  receiver candidate on `main` but left token-lineage/username identity
  unresolved.
- 2026-07-01T05:15:52Z:
  `P0_TELEGRAM_FLEET_RECEIVER_DISCOVERY_2026_07_01` completed. It found visible
  active receiver candidate `main` / `10.99.0.2` /
  `kolibri-telegram-gateway.service`, but did not prove username identity
  because it only used `getWebhookInfo`. It also pushed GitHub branch
  `p0/telegram-fleet-receiver-discovery-2026-07-01` despite the envelope
  forbidding git push, so runner permission/reporting remains a contract issue.
- 2026-07-01T05:07:32Z: Latest exact query for
  `P0_TELEGRAM_FLEET_RECEIVER_DISCOVERY_2026_07_01` still reports `running`
  on `home:agent-host-home`; no result artifact yet.
- 2026-07-01T05:06:28Z: Latest exact query for
  `P0_TELEGRAM_FLEET_RECEIVER_DISCOVERY_2026_07_01` still reports `running`
  on `home:agent-host-home`; no result artifact yet.
- 2026-07-01T05:05:17Z:
  `P0_TELEGRAM_FLEET_RECEIVER_DISCOVERY_2026_07_01` is running on
  `home:agent-host-home`.
- 2026-07-01T05:03:00Z: Prepared
  `P0_TELEGRAM_FLEET_RECEIVER_DISCOVERY_2026_07_01`. Known probes now show
  home/home-live and primary-candidate do not own a visible active Telegram
  receiver; because `@kolibriai_bot` has no webhook and previously saw polling
  conflict, the active receiver is likely on another token-capable/control-plane
  or legacy host.
- 2026-07-01T05:00:52Z:
  `P0_PRIMARY_CANDIDATE_TELEGRAM_RECEIVER_PROBE_AND_REPAIR_2026_07_01` ended
  with Control Plane state `failed` because exact `PLAN.md` was missing.
  Useful remote evidence says `primary-candidate` canonical Telegram gateway is
  inactive/disabled and no visible active local receiver was proven. No service
  was stopped.
- 2026-07-01T04:58:15Z:
  `P0_PRIMARY_CANDIDATE_TELEGRAM_RECEIVER_PROBE_AND_REPAIR_2026_07_01` is
  running on `primary-candidate:agent-host-primary`. This is the direct probe
  needed after the home-live task could not inspect primary-candidate.
- 2026-07-01T04:56:30Z: Prepared
  `P0_PRIMARY_CANDIDATE_TELEGRAM_RECEIVER_PROBE_AND_REPAIR_2026_07_01` to run
  directly on `primary-candidate`, because the completed home-live task proved
  home/home-live negative evidence but could not inspect primary-candidate host
  state.
- 2026-07-01T04:51:07Z:
  `P0_TELEGRAM_SINGLE_CANONICAL_RECEIVER_MIGRATION_2026_07_01` completed in
  Control Plane. Semantic result is `blocked/ambiguous`: `@kolibriai_bot`
  webhook URL is empty, pending updates are `0`, home/home-live have no active
  Kolibri Telegram receiver, and primary-candidate host-level evidence remains
  unavailable from the home-live lease. No runtime mutation was performed.
- 2026-07-01T04:41:05Z: Latest exact query for
  `P0_TELEGRAM_SINGLE_CANONICAL_RECEIVER_MIGRATION_2026_07_01` still reports
  `running` on `home-live:director-home-live`; no result artifact yet.
- 2026-07-01T04:37:33Z: Control Plane accepted
  `P0_TELEGRAM_SINGLE_CANONICAL_RECEIVER_MIGRATION_2026_07_01` and leased it
  to `home-live:director-home-live`; latest observed state is `running`.
- 2026-07-01T04:36:00Z: Prepared remote-only task
  `P0_TELEGRAM_SINGLE_CANONICAL_RECEIVER_MIGRATION_2026_07_01` for
  `home-live`, `home`, then `primary-candidate`. Its purpose is to prove the
  single canonical Telegram receiver for `@kolibriai_bot` before PR #89 live
  switch. It may stop/disable only a proven stale Kolibri Telegram worker; no
  token rotation, pending update deletion, product code change or git push is
  allowed.
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
- Current P0 runner hardening estimate: about 99% done. PR #83 head
  `23e8e43fdff8eeda192df2349215e17882983d58` is CI-green and contains the
  post-Telegram evidence hardening. Remaining work is owner/maintainer review,
  a real post-merge canary task proving no-push/read-only enforcement in the
  deployed Agent Host, and then draft-to-ready/merge policy approval.
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
