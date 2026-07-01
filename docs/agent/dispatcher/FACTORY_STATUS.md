# Factory Status

Snapshot time:
- 2026-07-01T09:15:43Z

Latest update:
- 2026-07-01T15:22:03Z:
  `P0_PR85_PROMPT3_FABRIC_API_SURFACE_REPAIR_2026_07_01` produced a useful
  remote implementation on `primary-candidate:agent-host-primary`. The Control
  Plane task state is `failed` only because the initial verifier checked for
  missing exact `PLAN.md`; the server worktree itself implemented the Prompt #3
  API surface, then exact `PLAN/ACTIONS/TESTS/RESULT/NEXT` artifacts were
  repaired on the same server worktree. Server verification passed: focused
  Fabric tests `11 passed`, full suite `71 passed, 1 warning`, `py_compile`
  passed and `git diff --check` passed. Server GitHub SSH push failed with
  `github.com:22 timeout`, so Mac acted only as thin-client relay for the
  server-created patch. PR #85 is now updated at head
  `06adeb54c0e7d7132c7f0817ea4755786cd3f092`, remains draft/mergeable, and
  GitHub Actions `Kolibri CI` run `28528330219` succeeded. Next exact task:
  `P0_PR85_RELEASE_GATE_AFTER_PROMPT3_SURFACE_REPAIR_2026_07_01`.
- 2026-07-01T15:00:00Z:
  Prepared remote implementation envelope
  `P0_PR85_PROMPT3_FABRIC_API_SURFACE_REPAIR_2026_07_01`. This follows PR
  #93's green review decision `repair_in_pr85` and targets PR #85 branch
  `p0/api-first-full-control-fabric-2026-07-01` at expected start head
  `9690361f02addeff37771c52fd37878aef455e13`. The task is remote-only,
  assigned to `Сергей — Fabric API Engineer`, and may modify product code only
  on PR #85 branch within Fabric API endpoint/schema/tests scope. It must add
  Prompt #3 `/v1/fleet/*`, `/v1/models`, `/v1/responses`,
  `/v1/chat/completions`, `/v1/agents/*`, deny-by-default `/v1/admin/*`,
  canonical envelope tests, fallback taxonomy tests, docs whitespace repair,
  and exact `PLAN/ACTIONS/TESTS/RESULT/NEXT` run artifacts. Mac has not
  implemented these changes locally. Control Plane accepted the task through
  `kolibri-primary-codex` at `2026-07-01T14:54:10Z` with HTTP 201 and initial
  state `queued`.
- 2026-07-01T14:22:08Z:
  Prepared remote-only release-gate envelope
  `2026-07-01-p0-fabric-api-pr85-gap-review`.
  This is the first concrete task after importing
  `docs/superfactory/Kolibri_All_Prompts.md` as the master canvas. The task
  must run on a server node, preferably `primary-candidate`, with Russian
  display name `Алексей — Fabric API Reviewer`. It compares
  canvas prompt #3 (`P0_KOLIBRI_UNIFIED_FABRIC_API_AND_SERVER_CONNECTIVITY`)
  against PR #85 at head
  `9690361f02addeff37771c52fd37878aef455e13`, which is open, draft,
  mergeable and GitHub Actions green. The task is review/docs-artifacts only:
  no product code, no PR #85 mutation, no merge, no deploy and no restart.
  Expected artifacts are exact `PLAN/ACTIONS/TESTS/RESULT/NEXT`, plus
  `FABRIC_PROMPT3_GAP_MATRIX.md` and
  `PR85_RELEASE_OR_REPAIR_DECISION.md`, all under
  `docs/agent/runs/2026-07-01-p0-fabric-api-pr85-gap-review/`.
  Direct Mac `ops/kolibri-dispatch submit` timed out, so submission used
  the documented server fallback route through `kolibri-primary-codex`.
  Control Plane accepted the task at `2026-07-01T14:27:03Z` with HTTP 201 and
  initial state `queued`. Exact polling shows the task is now `running` on
  `primary-candidate:agent-host-primary`, attempt
  `2026-07-01-p0-fabric-api-pr85-gap-review-attempt-1`, with heartbeat
  `2026-07-01T14:28:43.587861+00:00`. Result artifacts are not present yet,
  so completion is not claimed.
  Later exact polling returned `completed` with result reference
  `/var/lib/kolibri-agent/artifacts/2026-07-01-p0-fabric-api-pr85-gap-review/2026-07-01-p0-fabric-api-pr85-gap-review-attempt-1/result.json`.
  The source review produced a useful decision (`repair_in_pr85`) and pushed
  branch `p0/fabric-api-pr85-gap-review-2026-07-01`, but it created only
  `PR85_GAP_REVIEW.md`, not the eight exact owner-required files. Prepared
  follow-up `2026-07-01-p0-fabric-api-pr85-gap-review-artifact-repair` to
  repair artifacts remotely without product-code changes. Control Plane
  accepted the artifact repair at `2026-07-01T14:35:00Z` with HTTP 201 and
  initial state `queued`.
  The generic artifact repair also missed the exact owner filenames and failed
  on `PLAN.md`, but it produced useful server-side artifact material. A
  deterministic remote artifact alias repair then created the exact files on a
  clean server worktree. Server-side GitHub SSH push failed three times with
  `github.com:22 timeout`, so the Mac acted as a thin-client relay and pushed
  the server-created docs to GitHub. Draft PR #93 now records the review:
  `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/93`, head
  `27930696692ae6474b1c9add4062dca04b8fb3f1`, mergeable, with `Kolibri CI`
  run `28526155870` success. Final PR #85 release decision is
  `repair_in_pr85`; next exact task is
  `P0_PR85_PROMPT3_FABRIC_API_SURFACE_REPAIR_2026_07_01`.
- 2026-07-01T14:02:46Z:
  `P0_UIAP_MINIMAL_RAG_INDEXER_CONTRACT_2026_07_01` ran on
  `primary-candidate:agent-host-primary` and failed exact verification because
  the runner wrote useful docs under `docs/run-artifacts/...` and
  `docs/intelligence/P0_...`, not required `docs/agent/...` paths. The useful
  output has been relayed into exact local docs:
  `docs/agent/intelligence/2026-07-01-uiap-rag-indexer-contract/` and
  `docs/agent/runs/2026-07-01-p0-uiap-minimal-rag-indexer-contract/`.
  The contract keeps `uiap` internal-only: GitHub commit SHA source of truth,
  immutable ChromaDB collections, Control Plane trigger, future `/health` and
  `/search` shapes, and security/resource gates before production exposure.
- 2026-07-01T13:51:47Z:
  `P0_UIAP_RAG_SKILLS_REGISTRY_READINESS_2026_07_01` completed on
  `uiap:agent-host-uiap`. Result path:
  `/var/lib/kolibri-agent/artifacts/P0_UIAP_RAG_SKILLS_REGISTRY_READINESS_2026_07_01/P0_UIAP_RAG_SKILLS_REGISTRY_READINESS_2026_07_01-attempt-1/result.json`.
  The node reports CPU-only light RAG readiness: 2 cores, 3.8 GB RAM, about
  21 GB free, Python 3.12, Docker 28.1.1, sentence-transformers, ChromaDB,
  ONNX Runtime, torch CPU and transformers available. Safe next work is a
  minimal Markdown/skills indexer contract and ChromaDB collection. Do not send
  heavy models, GPU inference, large batch indexing, secret storage, Git pushes
  or long-running production workers to `uiap` yet.
- 2026-07-01T13:50:19Z:
  Owner instruction persistence was made durable in
  `docs/agent/dispatcher/OWNER_CANONICAL_INSTRUCTIONS.md` and pushed to
  dispatcher branch commit `43060cbd`. This separates durable GitHub memory
  from weaker session/model memory.

  Submitted read-only MIMO task
  `P0_UIAP_RAG_SKILLS_REGISTRY_READINESS_2026_07_01` through
  `kolibri-primary-codex -> Control Plane`. Control Plane accepted the task at
  `2026-07-01T13:48:19Z`; it is leased to `uiap:agent-host-uiap` and latest
  observed status is `running` with heartbeat `2026-07-01T13:50:19Z`. No
  result/reference yet, so it must not be called completed.
- 2026-07-01T13:33:00Z:
  Fleet role/capability inventory is now represented in GitHub as draft PR #92:
  `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/92`.
  Head `5a33c3fc0a5a434f40c6ed3783d8c73fe9557168` is mergeable and
  GitHub Actions run `28521289206` succeeded. The source Control Plane
  inventory task and canonical relay both produced useful server-side evidence
  but failed exact artifact verification because the generic runner wrote wrong
  paths/names. A deterministic docs-only alias repair normalized the output
  into exact run artifacts and intelligence files. The inventory confirms:
  `qjns`/`uiap` are no longer disk-blocked; `qjns` remains blocked for full
  work by GitHub credential and MIMO provider access; `uiap` is suitable for
  light RAG/knowledge work; `main` needs runner auth smoke; `home`/`home-live`
  need heartbeat freshness cleanup; stale mesh/metadata cards and queue
  retention need cleanup.
- 2026-07-01T13:05:00Z:
  GitHub PR #91 body was refreshed to match current source-of-truth state:
  head `350544492ce14a12865fb9a04e2abf6f87c87d3f`, draft, mergeable,
  GitHub Actions run `28518947833` success, artifact hygiene repaired, qjns
  credential blockers documented, and post-merge canary steps listed. Prepared
  but did not submit
  `docs/agent/dispatcher/envelopes/P0_PR91_POST_MERGE_MIMO_RUNNER_CANARY_2026_07_01.json`.
  Submit is intentionally gated on owner approval, PR #91 merge, and canary
  Agent Host deploy/restart.
- 2026-07-01T12:55:00Z:
  PR #91 artifact hygiene repair completed. Server task
  `P0_PR91_MIMO_RUNNER_ARTIFACT_HYGIENE_REPAIR_2026_07_01` pushed normal
  non-force commit `350544492ce14a12865fb9a04e2abf6f87c87d3f` to branch
  `p0/mimo-runner-output-auth-contract-repair-2026-07-01`. The PR no longer
  tracks top-level `artifacts/P0_MIMO_RUNNER_OUTPUT_AND_AUTH_CONTRACT_REPAIR_2026_07_01/*`.
  It now contains canonical run docs under
  `docs/agent/runs/2026-07-01-p0-mimo-runner-output-auth-contract-repair/`
  plus the intended code/test changes. GitHub source-of-truth check confirms
  PR #91 is open, draft, mergeable, head
  `350544492ce14a12865fb9a04e2abf6f87c87d3f`, and GitHub Actions run
  `28518947833` succeeded. Next action: owner release decision, then
  merge/deploy PR #91 and run direct MIMO fanout canary.
- 2026-07-01T12:54:11Z:
  qjns auth repair completed as a safe classification, not a blind credential
  mutation. Result:
  `P0_REPAIR_QJNS_GITHUB_AND_MIMO_AUTH_2026_07_01` is `completed` with
  artifact
  `/var/lib/kolibri-agent/artifacts/P0_REPAIR_QJNS_GITHUB_AND_MIMO_AUTH_2026_07_01/P0_REPAIR_QJNS_GITHUB_AND_MIMO_AUTH_2026_07_01-attempt-1/result.json`.
  GitHub on qjns is classified as `missing_node_github_credential`; MIMO on
  qjns is classified as `provider_access_denied`. qjns remains online with
  disk free about `8.26 GB`; this is no longer a disk issue. Next action is
  owner/provider credential restoration, then rerun bounded qjns clone and
  MIMO probes. No secrets were printed and no interactive login was attempted.

  PR #91 focused release verification also completed:
  `P0_PR91_MIMO_RUNNER_FOCUSED_RELEASE_VERIFIER_2026_07_01` verified exact
  head `a32697b62914816abfbd87365c7c1fec588b3262`; targeted tests passed:
  `9 passed in 2.17s`; `git diff --check` was clean. The verifier classified
  PR #91 as `needs changes before merge` because it tracks top-level
  `artifacts/` JSON files and those artifacts reference missing logs.
  Cleanup task `P0_PR91_MIMO_RUNNER_ARTIFACT_HYGIENE_REPAIR_2026_07_01` is now
  running on `primary-candidate:agent-host-primary` to move/normalize evidence
  into canonical `docs/agent/runs/...` and remove top-level artifacts from the
  PR branch.
- 2026-07-01T12:37:12Z:
  Fresh qjns/uiap status was rechecked through the server fallback route.
  Control Plane health is `ok`. `qjns` is online as `kolibri-tools-executor`
  with about 8.3 GB free on `/`, fresh Agent Host heartbeat, and
  implementation/review/qa capabilities. `uiap` is online as
  `kolibri-rag-knowledge` with about 22.9 GB free on `/` and has already
  completed a direct MIMO RAG/knowledge readiness response. Therefore the
  historical qjns/uiap disk blocker is repaired and should not be treated as
  the current blocker.

  Remaining qjns blockers are GitHub/MIMO auth, not disk. PR #91 review on
  qjns failed because `git clone https://github.com/...` could not read a
  username with terminal prompts disabled. Direct qjns MIMO still returned
  `403 illegal_access`. A new server-side repair task was submitted through the
  fallback command node after direct Mac dispatcher timeout:
  `P0_REPAIR_QJNS_GITHUB_AND_MIMO_AUTH_2026_07_01`. It is running on
  `primary-candidate:agent-host-primary` with branch
  `p0/repair-qjns-github-mimo-auth-2026-07-01`. It is constrained to use only
  approved existing credentials, avoid secret printing, avoid interactive
  login, avoid provider bypass, and avoid product code changes.
- 2026-07-01T12:11:34Z:
  Direct MIMO fanout was submitted through Control Plane, not executed on Mac.
  Seven child tasks were accepted. `uiap` completed a RAG/knowledge readiness
  response and `mesh-9fts` completed a read-only route probe. `main` confirmed
  MIMO auth failure with HTTP 401; no login or token refresh was attempted.
  `qjns` ran MIMO but hit a 403 `illegal_access` bootstrap blocker.
  `primary-candidate` produced useful JSON in stdout, but Agent Host marked it
  `runner_empty_response`, proving a MIMO parser/contract defect. `home` and
  `home-live` tasks remain queued without lease. Repair task
  `P0_MIMO_RUNNER_OUTPUT_AND_AUTH_CONTRACT_REPAIR_2026_07_01` completed on
  `primary-candidate`, moved to `waiting_review`, pushed commit
  `a32697b62914816abfbd87365c7c1fec588b3262`, and draft PR #91 is open:
  `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/91`.
  GitHub Actions run `28517063983` completed successfully.
- 2026-07-01T11:55:38Z:
  Fresh read-only verification corrected the `qjns/uiap` status. The disk
  repair is effective despite the historical Control Plane task state
  `failed`. `qjns` (`kolibri-tools-executor`) now shows `/` 19G total, 9.8G
  used, 8.2G free, Agent Host online, `/usr/local/bin/mimo` present and MIMO
  serve processes active. `uiap` (`kolibri-rag-knowledge`) now shows `/` 38G
  total, 15G used, 23G free, Agent Host online, `/usr/local/bin/mimo` present,
  MIMO serve active and two existing MIMO run processes. The remaining issue is
  artifact/verifier classification plus resource/GitHub-auth validation for
  heavier work, not disk space.
- 2026-07-01T09:27:00Z:
  Submitted read-only diagnostic
  `P0_AI_RUNNER_AUTH_AND_OWNER_REMOTE_TASK_ROUTING_DIAGNOSTIC_2026_07_01`
  through the server fallback route. Control Plane returned `201 Created`; exact
  task query shows state `running`, attempt
  `P0_AI_RUNNER_AUTH_AND_OWNER_REMOTE_TASK_ROUTING_DIAGNOSTIC_2026_07_01-attempt-1`,
  lease owner `primary-candidate:agent-host-primary`, branch
  `p0/ai-runner-auth-routing-diagnostic-2026-07-01`; heartbeat was fresh at
  `2026-07-01T09:21:41Z`. This task is constrained
  to diagnostics only: no credential changes, no login/token refresh, no secret
  printing, no product code changes, no git push and no heavy tests. Purpose:
  classify the `main` Codex `token_expired` and MIMO `runner_auth_failed`
  blockers and return the next safe repair task.
- 2026-07-01T09:25:00Z:
  Took a fresh read-only Control Plane snapshot through fallback route
  `kolibri-primary-codex -> http://10.99.0.2:9101`. Control Plane health is
  `ok`, Redis replies `PONG`, and `/v1/nodes` returns 42 node cards. Current
  online server/fabric cards include `home`, `home-live`, `main`,
  `primary-candidate`, `qjns`, `uiap`, `new`, `mesh-9fts`, `mesh-agent-03`,
  `mesh-home`, `mesh-main`, `mesh-new`, `mesh-primary`, `mesh-qjns` and
  `mesh-uiap`; several `mesh-agent-*` cards are `degraded`; the old direct
  `agent-01..09`/`9fts`/`paris`/`reserve242`/`server-kfrm` cards remain
  `stale`. Exact task queries confirm
  `P0_AGENT_HOST_REVIEW_CLONE_AND_CONSTRAINT_ENFORCEMENT_2026_07_01` and
  `P0_PR83_REVIEW_DIFF_CONTRACT_EXACT_ARTIFACT_CLEANUP_2026_07_01` are
  `completed`, while API-first/Command-Fabric/Telegram alignment tasks remain
  failed on exact-path verifier issues rather than total loss of work. GitHub
  CLI is installed at `/opt/homebrew/bin/gh` but not on the current shell PATH;
  using the full path confirms PR #83 is open, draft, mergeable, head
  `81daf44dc842dce40d8547275f47b051871a2690`, and `Kolibri CI` is successful.
  Open P0 PRs remain draft: #90, #89, #88, #87, #86, #85, #84 and #83. No PR
  was marked ready, merged, approved, or deployed from Mac.
- 2026-07-01T09:12:00Z:
  Refreshed GitHub connector evidence for PR #83. PR remains open, draft,
  mergeable, base `main` at `6d0317c52a9694448ee2c352dc196ce7a27b9487`,
  head `81daf44dc842dce40d8547275f47b051871a2690`, with `Kolibri CI` run
  `28504679530` success. Created owner release-gate packet
  `docs/agent/dispatcher/PR83_OWNER_DECISION_PACKET.md`. The packet notes that
  the PR body is stale, but Mac did not mutate the public PR, mark ready,
  approve, merge, push to `main`, or restart services. Next action is owner
  decision; after merge/deploy, submit
  `P0_AGENT_HOST_POST_MERGE_CONTRACT_CANARY_2026_07_01`.
- 2026-07-01T09:05:00Z:
  Ran deterministic read-only PR83 head verification on `primary-candidate`
  using the existing completed PR83 cleanup worktree at
  `81daf44dc842dce40d8547275f47b051871a2690`. Results:
  `python3 -m py_compile ops/agent_host.py tests/test_agent_host_runner_contract.py`
  passed, `python3 -m pytest tests/test_agent_host_runner_contract.py -q`
  returned `29 passed in 36.75s`, `git diff --check` passed, final git status
  was clean. Initial GitHub SSH fetch from the server timed out on port 22, so
  this was a verification of the already-present exact PR83 worktree, not a new
  fetch. Combined with GitHub Actions run `28504679530` success, PR83 has strong
  owner-decision evidence. It is still draft; Mac did not merge or mark ready.
  Prepared gated post-merge canary envelope
  `P0_AGENT_HOST_POST_MERGE_CONTRACT_CANARY_2026_07_01`, to submit only after
  owner merge/deploy/restart.
- 2026-07-01T08:57:00Z:
  Submitted final read-only PR #83 verification task
  `P0_PR83_FINAL_MERGE_READINESS_VERIFICATION_2026_07_01`.
  It ran on `primary-candidate:agent-host-primary` but ended
  `failed_useful_artifacts`: useful `RESULT.md`, `TESTS.md`, `NEXT.md`,
  `CHANGED_FILES.md` were created in the server worktree, but required exact
  `PLAN.md` and `ACTIONS.md` were missing, so Control Plane correctly failed.
  The server checkout also stayed at `origin/main` while the branch name was
  PR83, so local tests did not validate the PR head. GitHub connector from the
  dispatcher confirms current PR83 head
  `81daf44dc842dce40d8547275f47b051871a2690` has `Kolibri CI` run
  `28504679530` success. PR #83 is therefore at an owner release gate, not
  automation-merge-ready: owner must decide mark-ready/merge vs another repair.
  Record runner risks: no-push/read-only tasks still receive
  `full_autonomy`/`git_push`; checkout branch name can point at PR branch while
  HEAD remains at `main`; exact artifact enforcement is still brittle.
- 2026-07-01T08:46:00Z:
  PR83 artifact chain is now server-complete and GitHub-green. Cleanup task
  `P0_PR83_REVIEW_DIFF_CONTRACT_EXACT_ARTIFACT_CLEANUP_2026_07_01`
  completed on `primary-candidate`, pushed branch head
  `81daf44dc842dce40d8547275f47b051871a2690`, and GitHub Actions
  `Kolibri CI` run `28504679530` succeeded.
  Telegram official-capability alignment is not complete: stricter task
  `P0_TELEGRAM_COMMAND_CENTER_ALIGNMENT_RUN_PATH_RELAY_2026_07_01`
  failed because the generic runner again wrote wrong artifact paths
  (`REPORT.md` and `docs/product/.../runs/...`) instead of exact
  `OFFICIAL_CAPABILITY_ALIGNMENT.md` and `docs/agent/runs/.../*.md`.
  Do not repeat the same generic prompt. Next path is deterministic remote
  artifact relay or Agent Host exact-path enforcement fix.
- 2026-07-01T08:42:22Z:
  Submitted `P0_TELEGRAM_COMMAND_CENTER_ALIGNMENT_RUN_PATH_RELAY_2026_07_01`
  through `kolibri-primary-codex` after the previous Telegram relay wrote run
  docs into the product directory. Control Plane accepted the task but assigned
  `full_autonomy`/`git_push` permission pack despite the narrow docs-only
  envelope; record this as a runner contract risk.
- 2026-07-01T08:30:16Z:
  PR83 exact artifact repair produced useful uncommitted worktree changes
  (canonical `NEXT.md` added, `REMOTE_RESULT.json` removed), but Control Plane
  failed because the scope guard did not allow deletion of `REMOTE_RESULT.json`.
  Prepared cleanup task
  `P0_PR83_REVIEW_DIFF_CONTRACT_EXACT_ARTIFACT_CLEANUP_2026_07_01`.
  Telegram exact canonical relay is now running on `primary-candidate`.
- 2026-07-01T08:26:58Z:
  Submitted exact follow-ups through `kolibri-primary-codex`.
  `P0_PR83_REVIEW_DIFF_CONTRACT_EXACT_ARTIFACT_REPAIR_2026_07_01`
  is running on `primary-candidate:agent-host-primary` with fresh heartbeat.
  `P0_TELEGRAM_COMMAND_CENTER_ALIGNMENT_EXACT_CANONICAL_RELAY_2026_07_01`
  is queued.
- 2026-07-01T08:21:55Z:
  PR83 read-only diff contract repair pushed branch head
  `e2e27313e88ed8f285ccb057263dae6a5c447d2d`; GitHub Actions
  `Kolibri CI` run `28503501294` completed successfully. Control Plane task
  state remains `failed` because exact artifact `NEXT.md` was missing and
  `REMOTE_RESULT.json` was created instead. Prepared
  `P0_PR83_REVIEW_DIFF_CONTRACT_EXACT_ARTIFACT_REPAIR_2026_07_01`.
  Telegram canonical repair also failed verifier after writing useful output to
  non-canonical paths again; prepared strict exact canonical relay
  `P0_TELEGRAM_COMMAND_CENTER_ALIGNMENT_EXACT_CANONICAL_RELAY_2026_07_01`.
- 2026-07-01T08:13:19Z:
  Submitted `P0_TELEGRAM_COMMAND_CENTER_ALIGNMENT_CANONICAL_ARTIFACT_REPAIR_2026_07_01`;
  Control Plane accepted it as `queued`. Submitted
  `P0_PR83_REVIEW_PR_READ_ONLY_DIFF_CONTRACT_REPAIR_2026_07_01`;
  it is `running` on `primary-candidate:agent-host-primary` with fresh
  heartbeat. This keeps the runner-hardening P0 moving before PR #83 merge.
- 2026-07-01T08:09:58Z:
  Telegram official capability alignment task
  `P0_TELEGRAM_COMMAND_CENTER_OFFICIAL_CAPABILITY_ALIGNMENT_2026_07_01`
  failed the wrapper verifier after producing useful output in non-canonical
  paths (`docs/reports/...` and `artifacts/...`). Required canonical path
  `docs/product/telegram-command-center/2026-07-01/OFFICIAL_CAPABILITY_ALIGNMENT.md`
  was missing. Prepared docs-only repair task
  `P0_TELEGRAM_COMMAND_CENTER_ALIGNMENT_CANONICAL_ARTIFACT_REPAIR_2026_07_01`.
- 2026-07-01T08:05:57Z:
  PR83 fallback review produced useful exact artifacts and focused server tests
  passed, but Control Plane state is `failed` because the final wrapper verifier
  attempted `python3 -m py_compile ops/agent_host.py tests/test_agent_host_runner_contract.py`
  and the test path was missing in that checkout. The useful review found a real
  blocker: `review_pr` currently treats reviewed PR diff files as runner-authored
  changed files, so read-only review tasks can falsely block on product-code PRs.
  Prepared repair task
  `P0_PR83_REVIEW_PR_READ_ONLY_DIFF_CONTRACT_REPAIR_2026_07_01`.
- 2026-07-01T08:02:13Z:
  Submitted `P0_TELEGRAM_COMMAND_CENTER_OFFICIAL_CAPABILITY_ALIGNMENT_2026_07_01`
  through fallback route `kolibri-primary-codex -> http://10.99.0.2:9101/v1/tasks`.
  Control Plane accepted it as `queued`. It is waiting for a server lease and
  must only produce docs/artifacts, not live Telegram or product mutations.
- 2026-07-01T08:00:05Z:
  Prepared remote docs-only Telegram official capability alignment task
  `P0_TELEGRAM_COMMAND_CENTER_OFFICIAL_CAPABILITY_ALIGNMENT_2026_07_01`
  after the owner asked to study Telegram capabilities fully. The task targets
  `primary-candidate`/`home`/`home-live`, uses Russian display name
  `Иван — Telegram Platform Architect`, and forbids live Telegram mutation,
  product code changes, `getUpdates`, webhook/menu/BotFather changes,
  payments/Stars, Business, Guest Mode and Bot-to-Bot activation.
- 2026-07-01T07:58:01Z:
  Submitted fallback remote review task
  `P0_PR83_FINAL_REVIEW_AND_AGENT_HOST_CANARY_PLAN_2026_07_01`. Direct Mac
  Control Plane API timed out, then fallback through `kolibri-primary-codex`
  succeeded. Task is leased/running on `primary-candidate:agent-host-primary`.
- 2026-07-01T07:49:23Z:
  Prepared fallback remote review task
  `P0_PR83_FINAL_REVIEW_AND_AGENT_HOST_CANARY_PLAN_2026_07_01` for PR #83.
  Reason: automatic review task
  `P0_AGENT_HOST_BACKEND_VERIFIER_ENV_SCOPE_REPAIR_2026_07_01-REVIEW` routed
  to `new:agent-host-new` and failed clone twice with `git@github-kolibri`
  rc=128. Fallback task targets `primary-candidate`, is read-only/docs-artifacts
  only, and must not merge, mark PR ready, push, restart services or mutate
  runtime state. Goal: final PR #83 review against `origin/main` plus
  post-merge Agent Host canary plan.
- 2026-07-01T07:43:51Z:
  GitHub Actions evidence for PR #83 head
  `dfbc7fc17f4d76d81d97944a852febbb91278d9b`: `Kolibri CI` run
  `28501701336` completed with conclusion `success`. The `ci` job succeeded,
  including Python syntax compile, pytest, JavaScript/TypeScript checks,
  JSON/YAML validation, secret scan, production secret path guard and local
  component smoke.
- 2026-07-01T07:41:39Z:
  `P0_AGENT_HOST_BACKEND_VERIFIER_ENV_SCOPE_REPAIR_2026_07_01` produced a
  completed result and Control Plane moved the task endpoint to
  `waiting_review`. Result artifact:
  `/var/lib/kolibri-agent/artifacts/P0_AGENT_HOST_BACKEND_VERIFIER_ENV_SCOPE_REPAIR_2026_07_01/P0_AGENT_HOST_BACKEND_VERIFIER_ENV_SCOPE_REPAIR_2026_07_01-attempt-1/result.json`.
  The server found PR #83 branch head `4b8d2a9...` already satisfied the
  implementation contract, reran focused tests (`28 passed in 32.66s`), added
  only exact repair artifacts under
  `docs/agent/runs/2026-07-01-p0-agent-host-backend-verifier-env-scope-repair/`,
  and pushed normal branch head
  `dfbc7fc17f4d76d81d97944a852febbb91278d9b`. Main was not touched.
- 2026-07-01T07:34:05Z:
  Prepared `P0_AGENT_HOST_BACKEND_VERIFIER_ENV_SCOPE_REPAIR_2026_07_01`.
  Reason: `P0_AGENT_HOST_BACKEND_VERIFIER_ENV_CONTRACT_2026_07_01` produced a
  useful PR #83 branch head `4b8d2a9f431034963945ffc929a7c19e3c7ff640` and
  server focused tests passed (`28 passed in 36.62s`), but Control Plane
  correctly failed final verification because the envelope change-scope guard
  omitted `.gitignore` and `docs/agent/AGENT_RUNNER_CONTRACT.md`. The repair
  task will verify or minimally repair the same PR #83 branch with corrected
  allowed scope and exact run artifacts.
- 2026-07-01T07:32:49Z:
  `P0_AGENT_HOST_BACKEND_VERIFIER_ENV_CONTRACT_2026_07_01` ended with Control
  Plane state `failed`. Useful output: backend verifier environment contract
  implementation was pushed normally to PR #83 branch head
  `4b8d2a9f431034963945ffc929a7c19e3c7ff640`; remote stdout reports
  `python3 -m pytest tests/test_agent_host_runner_contract.py -q` -> `28
  passed in 36.62s`. Failure reason: final verifier changed-file guard only
  allowed `ops/agent_host.py`, `tests/test_agent_host_runner_contract.py` and
  the first run docs, but the server implementation also touched `.gitignore`
  and `docs/agent/AGENT_RUNNER_CONTRACT.md`. Do not call this task completed;
  repair via corrected-scope verifier.
- 2026-07-01T07:17:21Z:
  Prepared `P0_AGENT_HOST_BACKEND_VERIFIER_ENV_CONTRACT_2026_07_01` for the
  PR #83 runner-hardening branch. Purpose: add an explicit backend Python
  verification environment contract to Agent Host so backend verifier commands
  can run with `backend/requirements.txt` plus pytest in a temporary
  dependency-satisfied environment. This is the direct follow-up to PR #90,
  where raw system Python lacked `fastapi` but the declared backend test env
  passed.
- 2026-07-01T07:12:15Z:
  `PR90_EXACT_ARTIFACT_RELAY_2026_07_01` completed as a deterministic
  thin-client relay. PR #90 branch is now at
  `0fb48df868991ce2d23f326b87fe0e09e118bc3f`; exact canonical artifacts exist
  under
  `docs/agent/runs/2026-07-01-p0-telegram-miniapp-owner-auth-contract/`.
  Relay checks: exact files present, `git diff --check` clean, secret-pattern
  scan clean. GitHub connector fetched the commit diff; combined status list is
  empty, so CI/check status is not claimed.
- 2026-07-01T07:09:56Z:
  `P0_TELEGRAM_AUTH_PR90_CANONICAL_ARTIFACTS_AND_ENV_VERIFIER_2026_07_01`
  ended with Control Plane state `failed`. Useful output: server branch head
  `133f698fc978e1632e83909cbb25016cedadc275`, dependency-satisfied root auth
  verifier `8 passed`, and system Python blocker `ModuleNotFoundError: No
  module named 'fastapi'`. Failure reason: the remote agent wrote
  `PLAN.md/ACTIONS.md/TESTS.md/RESULT.md/NEXT.md` at repo root, while verifier
  required them under `docs/agent/runs/2026-07-01-p0-telegram-miniapp-owner-auth-contract/`.
- 2026-07-01T07:06:03Z:
  `P0_TELEGRAM_AUTH_PR90_CANONICAL_ARTIFACTS_AND_ENV_VERIFIER_2026_07_01`
  is running on `primary-candidate:agent-host-primary`. Attempt
  `P0_TELEGRAM_AUTH_PR90_CANONICAL_ARTIFACTS_AND_ENV_VERIFIER_2026_07_01-attempt-1`
  writes artifacts under
  `/var/lib/kolibri-agent/artifacts/P0_TELEGRAM_AUTH_PR90_CANONICAL_ARTIFACTS_AND_ENV_VERIFIER_2026_07_01/`.
- 2026-07-01T07:05:22Z:
  Control Plane accepted
  `P0_TELEGRAM_AUTH_PR90_CANONICAL_ARTIFACTS_AND_ENV_VERIFIER_2026_07_01`.
  Initial state is `queued`; lease owner is not assigned yet.
- 2026-07-01T07:04:00Z:
  Prepared
  `P0_TELEGRAM_AUTH_PR90_CANONICAL_ARTIFACTS_AND_ENV_VERIFIER_2026_07_01`.
  It is docs/artifact and verification only: exact
  `PLAN/ACTIONS/TESTS/RESULT/NEXT` artifacts for PR #90 plus a verifier command
  that creates a temporary backend test environment before running
  `tests/test_telegram_miniapp_auth.py`. Write scope excludes backend, tests,
  frontend, ops, infra, GitHub Actions and dispatcher files.
- 2026-07-01T07:01:57Z:
  `P0_TELEGRAM_MINIAPP_OWNER_AUTH_VERIFIER_REPAIR_2026_07_01` ended with
  Control Plane state `failed`. Useful output exists: Draft PR #90
  `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/90` and branch
  head `378b19db9ca2b509d140ab241a67268f291b4c45`. It added
  `tests/test_telegram_miniapp_auth.py` and proved the dependency-satisfied
  root verifier path in a temporary venv (`8 passed`) plus gateway tests
  (`31 passed`). Final wrapper correctly failed because raw system Python on
  `primary-candidate` lacks `fastapi` from `backend/requirements.txt`. Read-only
  branch inspection also shows canonical run artifacts are still not exact:
  branch contains `01_scope.txt` through `05_remote_result.json`, not
  `PLAN.md`, `ACTIONS.md`, `TESTS.md`, `RESULT.md`, `NEXT.md`.
- 2026-07-01T06:56:48Z:
  `P0_TELEGRAM_MINIAPP_OWNER_AUTH_VERIFIER_REPAIR_2026_07_01` is running on
  `primary-candidate:agent-host-primary`. Attempt
  `P0_TELEGRAM_MINIAPP_OWNER_AUTH_VERIFIER_REPAIR_2026_07_01-attempt-1`
  writes artifacts under
  `/var/lib/kolibri-agent/artifacts/P0_TELEGRAM_MINIAPP_OWNER_AUTH_VERIFIER_REPAIR_2026_07_01/`.
  Expected proof: exact root-level `tests/test_telegram_miniapp_auth.py`,
  exact five run docs, focused tests, normal branch push, and no frontend/ops
  or live Telegram mutation.
- 2026-07-01T06:56:01Z:
  Control Plane accepted
  `P0_TELEGRAM_MINIAPP_OWNER_AUTH_VERIFIER_REPAIR_2026_07_01` through the
  `kolibri-primary-codex` route. Initial state is `queued`; lease owner and
  result artifact are not assigned yet. The task targets the existing branch
  `p0/telegram-miniapp-owner-auth-contract-2026-07-01` and may push only that
  branch.
- 2026-07-01T06:56:00Z:
  `P0_TELEGRAM_MINIAPP_OWNER_AUTH_CONTRACT_2026_07_01` finished with
  Control Plane state `failed`, and that status is correct. The remote agent
  pushed useful backend-only branch
  `p0/telegram-miniapp-owner-auth-contract-2026-07-01` at
  `3d221079d167ffc5c9cdfd3a240b02709a00074c`, but final verifier ran
  `python3 -m pytest tests/test_telegram_miniapp_auth.py -q` and failed
  because the test was created under `backend/tests/test_telegram_miniapp_auth.py`.
  Remote useful test evidence reported `8 passed` for the backend auth tests,
  `31 passed` for `tests/test_telegram_gateway.py`, and `2 passed` for
  `backend/tests/test_factory_status_fast_health.py`. Prepared follow-up
  `P0_TELEGRAM_MINIAPP_OWNER_AUTH_VERIFIER_REPAIR_2026_07_01` to repair the
  branch contract with exact root-level verifier path and exact
  `PLAN/ACTIONS/TESTS/RESULT/NEXT` run artifacts. No product code was changed
  on Mac.
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
  Artifact stdout and a fresh 2026-07-01T11:55Z check show effective repair
  succeeded: `qjns` has ~8.2 GB free and `uiap` has ~23 GB free. Do not treat
  these nodes as disk-blocked.
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
- `qjns`: online; fresh `df -h` observed 8.2 GB free on `/`; Agent Host and
  MIMO are present. Use for light executor/MIMO tasks first.
- `uiap`: online; fresh `df -h` observed 23 GB free on `/`; Agent Host and
  MIMO are present. Prefer for RAG/knowledge/security tasks and avoid heavy
  builds until memory pressure is reviewed.
- `main`: online; current free disk observed `7614488576` bytes; known
  Codex/MIMO runner auth is broken. Fresh MIMO direct recheck confirmed HTTP
  401 auth failure without attempting login or token refresh.
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

2026-07-01T10:16Z owner-facing production notes:
- Telegram GoMesh report message formatting was implemented remotely on PR #89
  branch head `e14aae215e0025a55509c0d7201ff5e192da32e6`; GitHub Actions
  `Kolibri CI` run `28509984338` succeeded and remote Telegram gateway tests
  reported `36 passed`. Control Plane task state is still `failed` because the
  verifier required exact `PLAN.md`/`ACTIONS.md` aliases that were not created.
  The formatter is not proven live on the current main Telegram receiver until
  PR #89 or a narrow live-safe backport is deployed.
- Production factory panel endpoint was repaired on `plastilin`: public
  `https://kolibriai.ru/api/factory/status` now returns `200 application/json`
  with `status=online`, `source=control-plane`, `total_nodes=42`,
  `online_nodes=20`. Public `https://kolibriai.ru/?telegram=1` still returns
  `200 text/html`. The repair is a tactical nginx exact-route exception to
  `http://10.99.0.2:8000/api/factory/status`; rollback backup is
  `/etc/nginx/kolibri-backups/kolibri.bak-factory-status-20260701T101154Z`.
  Control Plane task state is `failed` only because the lease environment lacks
  `pytest` for the requested verifier command.

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
- MIMO runner contract repair is now in PR #91 and CI is green. Until deployment passes,
  primary-candidate/qjns MIMO results can still be misclassified on the live
  Agent Host.

Known fleet notes from current owner context:
- Owner-facing server set is 20 servers; latest emergency SSH probe reached
  all 20.
- Control Plane currently exposes 42 node cards because it includes mesh,
  stale and metadata cards in addition to the owner-facing server set.
- `qjns` and `uiap` disk pressure is confirmed repaired. Retention cleanup,
  GitHub auth validation and per-node resource limits remain follow-up tasks.
