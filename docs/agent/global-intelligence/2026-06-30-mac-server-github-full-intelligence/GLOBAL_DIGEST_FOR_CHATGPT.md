# Kolibri Factory - global intelligence digest for ChatGPT

Дата снимка: 2026-06-30.
Репозиторий на Mac: `/Users/kolibri/.codex/worktrees/065e/kolibri-ai-platform`.
Главная цель: дать ChatGPT полный контекст по локальной машине, GitHub, Control Plane и всем 20 серверным узлам, чтобы следующие задачи не стартовали вслепую.

## 1. Что такое Kolibri Factory

Kolibri Factory - это распределенная AI/platform factory для разработки и запуска Kolibri AI Platform: backend/API, frontend/PWA, Telegram-интеграции, Control Plane, Agent Host, mesh/runtime workers, deterministic estimates, documents/PDF, billing scaffold, LLM provider stack и серверные automation runners.

Проект живет сразу в трех плоскостях:

- GitHub как source of truth для веток, PR, CI и issues.
- Mac как локальная dev station и command center. Последняя пользовательская постановка явно разрешает анализ и разработку на Mac, то есть прежний режим "Mac thin client only" для этой задачи переопределен.
- Серверный Control Plane как runtime/dispatch среда для тяжелых, remote-only и multi-node задач.

## 2. Как устроен проект

Текущий `origin/main` уже содержит несколько ключевых слоев:

- `backend/` - FastAPI/API, provider adapter, estimates, documents, PDF generation, tests.
- `frontend/` - PWA/UI shell.
- `ops/` - Control Plane, Agent Host, Telegram gateway, mesh bridge, install scripts, systemd integration.
- `infra/` - network/mesh/organism API.
- `scripts/` - training and helper scripts, включая Qwen2.5 LoRA/FormulaLM-related training path.
- `.github/workflows/ci.yml` - основной GitHub Actions workflow `Kolibri CI`.
- `docs/` - агентные отчеты, intelligence artifacts, handoffs и operational notes.
- `tests/` - runtime/API/factory tests.

Серверный runtime местами богаче, чем локальный `main`: на серверах есть live Control Plane queue, agent messages, node cards, systemd services, runtime repos и artifact directories.

## 3. Основные директории и сервисы

Основные директории:

- `backend/`: API routes, provider stack, estimate/document/PDF engines.
- `frontend/`: PWA/frontend app.
- `ops/factory_control.py`: Control Plane.
- `ops/agent_host.py`: Agent Host and runner logic.
- `ops/mesh_control_bridge.py`: mesh/control bridge.
- `ops/telegram_gateway.py`: Telegram gateway and reporting/chat flow.
- `ops/systemd/`: systemd unit files.
- `infra/network/`: network and organism API.
- `scripts/training/`: Qwen/LoRA/FormulaLM-style training scripts.
- `docs/agent/`: operational artifacts and intelligence packs.

Live services seen on servers:

- `kolibri-factory-control`
- `kolibri-agent-host`
- `kolibri-agent-host@mesh-agent-01`
- `kolibri-agent-host@mesh-agent-02`
- `kolibri-agent-host@mesh-agent-03`
- `kolibri-mesh-control-bridge`
- `kolibri-mesh-agent`
- `kolibri-ai`
- `kolibri-frontend-dev`
- `kolibri-network`
- `kolibri-docs-portal`
- `codex-remote-control.service`

## 4. Языки и технологии

Найдены и используются:

- Python/FastAPI-like backend and ops scripts.
- Node/npm frontend/PWA.
- Rust toolchain present locally, but core current app scan is Python/Node heavy.
- Docker available locally and on `primary-candidate`.
- systemd services for runtime.
- Redis-backed Control Plane health and queue.
- GitHub Actions CI.
- AI/LLM providers and related concepts in code/branches/issues: OpenAI-compatible, Kimi, MiMo/Mimo, Yandex, Google/Gemini, Ollama, vLLM, LiteLLM, MCP, RAG, embeddings, image generation.
- Qwen2.5 LoRA training path in `scripts/training/`.

## 5. Build/test/deploy commands найденные по проекту

Команды/проверки, которые фигурируют в repo/PR/context:

- `npm install`, `npm run build` for frontend.
- Python tests via pytest-style test paths, especially backend/factory tests.
- GitHub Actions workflow `Kolibri CI`.
- systemd deploy/start/status through units in `ops/systemd/`.
- Control Plane dispatch through `ops/kolibri-dispatch`.
- Training scripts under `scripts/training/`.
- Server runtime checks through Control Plane health endpoint and systemd.

Тяжелые builds/tests/inference/training не запускались в этом scan: задача была read-only intelligence.

## 6. Ветки

Снимок branch inventory:

- local branches: 31.
- remote tracking branches: 70.
- remote-only heads discovered through GitHub/ls-remote style data: 25.
- total global branch matrix rows: 126.
- worktrees listed on Mac: 30.

Текущий Mac worktree:

- branch: detached `HEAD`.
- HEAD: `6d0317c52a9694448ee2c352dc196ce7a27b9487`.
- commit subject: `Merge pull request #45 from rd8r8bkd9m-tech/codex/version-mesh-control-bridge`.
- dirty state: only untracked `docs/`; no tracked product diff and no staged diff.

## 7. Что в main

`origin/main` is at `6d0317c5`, same commit as current detached Mac worktree. It includes PR #45/version mesh control bridge and recent Telegram/mesh/factory work. Local branch `main` in one older worktree is stale at `93502e46` and is behind `origin/main` by roughly 14 commits.

`main` is currently the safest baseline for new small fixes, but do not checkout over a dirty worktree. Use a safe new worktree/branch.

## 8. Что в primary-candidate

Server `primary-candidate` is a real runtime/control standby node, but its runtime repo is not clean:

- host: `kolibri`.
- repo: `/var/lib/kolibri-agent/runtime-repo`.
- branch: `codex/version-mesh-control-bridge`.
- HEAD: `ad947ba`.
- status: behind `origin/main` by about 3 commits.
- dirty tracked files: `backend/providers.py`, `infra/network/api.py`, `infra/network/organism.py`, `ops/agent_host.py`, `ops/factory_control.py`, `ops/telegram_gateway.py`, `tests/test_factory_runtime.py`.
- services: primary/control standby services are active, including agent-host instances and docs portal.

Risk: this node has useful live runtime state, but its dirty product changes must be audited before using it as a merge source.

## 9. Что в qjns

`qjns` is visible in Control Plane as an online/fresh node:

- node_id: `qjns`.
- hostname: `kolibri-tools-executor`.
- agent: `agent-host-qjns`.
- capabilities: `read_only_probe`, `implementation`, `review`, `qa`, `agent-host`.
- CPU: 1.
- RAM available around 533 MB at scan time.
- disk free reported by node card: `0.0 GB`.

Direct SSH from Mac to `qjns` timed out through the configured path. Prior/session memory and issue context indicate qjns clone/auth failures and task index drift. Treat qjns as P0 degraded until disk and GitHub auth are fixed.

## 10. Свежие, старые, опасные, merge-ready ветки

Merge-ready or nearly ready:

- `origin/main`: current baseline, CI-relevant, latest local detached HEAD.
- `p0/telegram-miniapp-kolibriai-deploy` / PR #61: ready, base `main`, CI success, merge state clean, medium risk due deploy/runtime surface.
- PR #81 `codex/telegram-live-director-primary`: draft, clean, CI success, but still draft.
- PR #60 agent runtime smoke result capture: clean, CI success, base `codex/factory-autonomy-pwa-billing`.

High-risk / split-needed:

- `codex/factory-autonomy-pwa-billing`: local head `bcb7f29b`, remote PR #46 head `6231f706`, 40-52 commits ahead depending ref, about 262-270 changed files. Contains PWA, billing scaffold, factory autonomy, deterministic estimates, FormulaLM harness and docs. Must be split before merge.
- `codex/formulalm-rd-integration-20260629`: about 41 commits ahead and 268 changed files. Research/training branch, remote-only validation needed.
- `codex/factory-ha-spool-20260627`: important factory/HA work, but needs rebasing/audit.
- runtime server branch on `primary-candidate`: dirty and behind `main`.

Old/cleanup candidates:

- many `agent/TG-*` and early `factory/*` remote branches are likely historical task branches. Inspect for artifacts before archiving.
- prunable tmp worktrees under `/private/tmp` and one Codex worktree can be cleaned later, but not in this read-only task.

## 11. Dirty working tree сейчас

Mac current worktree:

- `git status --short --branch`: `## HEAD (no branch)` and `?? docs/`.
- `git diff --stat`: empty.
- staged diff: empty.
- classification: docs-only untracked artifact generation, no product code changes.

Server dirty runtime repos:

- `main` server `/var/lib/kolibri-agent/runtime-repo`: modified `ops/factory_control.py`, `ops/mesh_control_bridge.py`, untracked backup `ops/factory_control.py.bak-20260628T015641Z`.
- `primary-candidate` server runtime repo: multiple tracked product files dirty, listed above.

## 12. Изменения по подсистемам

Main/merged baseline:

- Control Plane and mesh bridge are active and recently changed.
- Telegram gateway and live Telegram chat/reporting flow are central.
- Backend has estimates/documents/PDF engines and provider adapter.
- Frontend/PWA exists but larger PWA/billing/autonomy work is mostly in PR #46.

PR #46 / `codex/factory-autonomy-pwa-billing`:

- PWA refactor.
- T-Bank billing scaffold.
- factory autonomy contracts, generic runner, role catalog.
- deterministic estimates.
- FormulaLM remote-only harness.
- validation in PR body: 21 tests passed, frontend build passed, Mac FormulaLM intentionally blocked.

Runtime/server:

- Control Plane queue, node cards and agent messages exist live.
- `/v1/filesystem` previously returned 404.
- queue was large/truncated.
- task artifact path/write-scope drift is present in recent failed tasks.

## 13. Что уже сделано

- Mac repo, worktrees, branches, dirty tree and local artifacts scanned read-only.
- GitHub repo, open PRs, CI workflow, recent CI runs, issues and branch protection access checked read-only.
- 20 server nodes analyzed through Control Plane node cards.
- Direct SSH mini-scan attempted for all 20; only `main` and `primary-candidate` were reachable from Mac.
- Existing server task `2026-06-30-full-project-scan-for-chatgpt` was observed as completed on `primary-candidate`.
- Local intelligence artifacts from previous scans were indexed.
- This global intelligence pack was created under `docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/`.

## 14. Что выполняется

At snapshot time:

- Control Plane and agent-host services are running on `main` and `primary-candidate`.
- Node cards show all 20 target nodes fresh/online or degraded-fresh in CP.
- CP queue has backlog and truncation.
- Several GitHub PRs remain open/draft and CI has mostly green recent runs.

## 15. Что заблокировано

Main blockers:

- `uiap` and `qjns` report `0.0 GB` free disk in Control Plane cards.
- Direct SSH from Mac times out to 18 of 20 server aliases, likely jump/firewall/VPN/routing issue.
- Server repos cannot use GitHub HTTPS non-interactively: `fatal: could not read Username for 'https://github.com': terminal prompts disabled`.
- P0 integration contract audit failed because expected artifacts were missing; repair task also failed because runner wrote wrong filenames/paths.
- Generic runner contract is not strict enough about `write_scope`, artifact verification and no-push constraints.
- Control Plane task list is large/truncated and has dispatchability problems.
- Local full mirror clone attempt from GitHub hung/timed out, so branch analysis used local refs plus remote metadata.

## 16. Где Control Plane

Repo path:

- `ops/factory_control.py`

Runtime:

- `main`: `kolibri-factory-control` active, CP health OK, Redis PONG.
- `primary-candidate`: `kolibri-factory-control` active in standby/control role.

Known endpoints/behaviors:

- health endpoint accessible from server side.
- `/v1/tasks` returned large/truncated queue.
- `/v1/agent-messages` exists in live runtime.
- `/v1/filesystem` previously returned 404.

## 17. Где Agent Host

Repo path:

- `ops/agent_host.py`

Runtime:

- `main`: `kolibri-agent-host` active.
- `primary-candidate`: `kolibri-agent-host` and `kolibri-agent-host@mesh-agent-01/02/03` active.
- node cards show multiple `agent-host-*` agents with capabilities like `generic_implementation`, `review`, `qa`, `runner:codex`, `runner:mimo`.

Key issue:

- runner must be hardened before more important audits: enforce no-push, enforce write_scope/artifact directory, verify required output files before commit/push/result success.

## 18. Где FormulaLM

Current local baseline:

- no isolated `FormulaLM` product module was found in `main`.
- training/scientific path appears under `scripts/training/` with Qwen2.5 LoRA style scripts.
- backend benchmark/provider hooks are present but parts are stubs/empty in local baseline.

Branches/PR:

- `codex/formulalm-rd-integration-20260629` is large/high-risk.
- PR #46 says FormulaLM remote-only harness exists there and Mac FormulaLM benchmark is intentionally blocked.
- Issue #63 says FormulaLM remote-only benchmark guard is not enforceable yet.

## 19. Где Telegram reporting

Repo paths:

- `ops/telegram_gateway.py`
- Telegram-related logic in `ops/agent_host.py`

Branch/PR context:

- PR #61: P0 Telegram miniapp/director deploy.
- PR #81: live Telegram dialog without TGCHAT tasks, draft and CI green.
- many historical `agent/TG-*` branches hold Telegram task artifacts.

## 20. Где estimates

Repo paths:

- `backend/estimate_engine.py`
- `backend/document_engine.py`
- `backend/pdf_engine.py`
- `backend/tests/test_estimate_document_pdf_engines.py`

Context:

- deterministic estimates are part of PR #46.
- construction estimate/document generation is a core product path.

## 21. Где billing

Baseline `main` scan did not show a complete billing subsystem in the current tree. Billing is primarily in the large PR #46 scope:

- PR #46 body mentions T-Bank billing scaffold.
- This must not be mixed with unrelated PWA, FormulaLM and factory autonomy changes in one final merge PR.

## 22. Где frontend/PWA

Repo path:

- `frontend/`

Context:

- local root contains `frontend/package.json`.
- PR #46 contains a large PWA refactor.
- `kolibri-frontend-dev` service is active on `main` server.

## 23. Где DevOps/bootstrap

Repo/runtime paths:

- `ops/systemd/`
- `ops/install-telegram-secret.sh`
- `ops/kolibri-dispatch`
- server runtime repos under `/var/lib/kolibri-agent/runtime-repo`
- artifacts under `/var/lib/kolibri-agent/artifacts/`

Do not print env values or secret files. Secret installation scripts may exist, but values were not printed.

## 24. Где AI/LLM integrations

Known areas:

- `backend/providers.py`
- `backend/adapter.py`
- provider-related tests and route hooks.
- Kimi integration PR #36 is green.
- Mimo runner exists in node capabilities and server tools.
- OpenAI-compatible/Yandex/Gemini/Ollama/vLLM/LiteLLM/MCP/RAG/embeddings/image generation are present in branch/task/issue/provider context and should be audited per subsystem before consolidation.

## 25. Главные риски

1. Giant PR #46 mixes too many product and factory surfaces.
2. Runtime repos on servers are dirty and can diverge from GitHub.
3. Agent runner already violated expected artifact path behavior in P0 audit/repair tasks.
4. A previous full-scan server task reportedly pushed a branch despite no-push style constraints, so runner policy enforcement is suspect.
5. `uiap` and `qjns` have no disk reserve.
6. Direct Mac SSH cannot reach most servers.
7. GitHub auth on servers is broken for noninteractive HTTPS clone/fetch.
8. CP queue is large/truncated and dispatchability is degraded.
9. FormulaLM boundary is unclear between training scripts, provider hooks and benchmark harness.
10. Billing scaffold is mixed with PWA/autonomy branch.
11. Local `main` branch is stale in one worktree while detached worktree is current.
12. Too many old branches/worktrees increase merge and context risk.

## 26. Главные blockers

- Fix disk reserve on `uiap` and `qjns`.
- Harden Agent Host generic runner contract.
- Fix server GitHub auth/clone flow without exposing secrets.
- Restore direct/admin reachability or document correct jump path for all 20 servers.
- Split PR #46 into reviewable PRs.
- Cleanly preserve and audit dirty runtime changes from `main` and `primary-candidate`.

## 27. Что ChatGPT должен прочитать первым

Recommended first files:

1. `docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/GLOBAL_DIGEST_FOR_CHATGPT.md`
2. `docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/SERVER_CLUSTER_READINESS.md`
3. `docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/ALL_BRANCHES_GLOBAL_MATRIX.md`
4. `docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/RISK_REGISTER.md`
5. `docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/NEXT_DEVELOPMENT_TASKS.md`
6. `docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/PROJECT_DIGEST_FOR_CHATGPT_LOCAL.md`
7. `docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/LOCAL_WORKTREE_INTELLIGENCE.md`
8. `docs/agent/intelligence/2026-06-30-full-project-scan-for-chatgpt/SUBMISSION_STATUS.md`
9. `README.md`
10. `.github/workflows/ci.yml`
11. `ops/factory_control.py`
12. `ops/agent_host.py`
13. `ops/telegram_gateway.py`
14. `backend/providers.py`
15. `backend/estimate_engine.py`
16. `frontend/package.json`

## 28. Следующие задачи для агентов

Highest priority:

1. P0 harden Agent Host generic runner contract: no-push enforcement, write_scope enforcement, artifact path validation, required file verification before success.
2. P0 restore disk reserve on `uiap` and `qjns`.
3. P0 fix noninteractive GitHub clone/fetch auth on server nodes without printing tokens.
4. P0 fetch/preserve dirty runtime diffs from `main` and `primary-candidate` into safe audit artifacts.
5. Split PR #46 into separate PRs: PWA, billing, factory runner/contracts, deterministic estimates, FormulaLM harness.
6. Rerun integration contract audit after runner hardening.
7. Build server reachability map and correct SSH/jump/VPN routes for all 20 nodes.

## 29. Что нельзя смешивать в один PR

Do not mix:

- PWA/frontend refactor with billing.
- Billing with FormulaLM/training.
- FormulaLM/training with Control Plane runner changes.
- Control Plane runner hardening with Telegram UX changes.
- Telegram miniapp/director deploy with backend provider stack changes.
- Dirty runtime server recovery with product feature work.
- DevOps/systemd bootstrap changes with estimate/PDF product changes.
- GitHub auth/server credential fixes with application code.

## 30. Следующий правильный Control Plane task

Recommended next Control Plane task:

`P0_AGENT_HOST_GENERIC_RUNNER_CONTRACT_HARDENING_2026_06_30`

Goal:

Harden Agent Host generic runner so every remote task enforces read-only/no-push/write-scope/artifact-directory constraints, verifies required output files before reporting success, and returns structured blocker reports when requirements cannot be met.

Why this is next:

The factory cannot safely run audits or implementation tasks if runner success can drift from actual artifact paths, if no-push constraints are not enforced, or if missing files are discovered only after the task is marked complete/failed inconsistently.

Acceptance:

- task envelope supports explicit `write_scope`, `required_artifacts`, `git_push_forbidden`, `product_code_modification_forbidden`, `read_only`.
- runner refuses to commit/push when forbidden.
- runner fails before success if required files are absent.
- runner emits a structured `blocked` result for unsupported kind/capability.
- add tests for P0 audit/repair artifact path cases.
- rerun `2026-06-30-p0-integration-contract-audit` after fix.

```yaml
project: Kolibri Factory
task_id: 2026-06-30-mac-server-github-full-intelligence
mac_hostname: MacBook-Air-Vladislav.local
mac_role: dev_station_and_command_center
server_role: remote_workers_control_plane_heavy_validation
github_role: source_of_truth_for_branches_pr_ci
repo_root: /Users/kolibri/.codex/worktrees/065e/kolibri-ai-platform
default_branch: main
current_mac_branch: detached_HEAD
current_mac_head: 6d0317c52a9694448ee2c352dc196ce7a27b9487
current_mac_dirty_state: docs_only_untracked
branches_analyzed:
  local: 31
  remote_tracking: 70
  remote_ls_remote_only: 25
  total_matrix_rows: 126
worktrees_listed: 30
github:
  accessible: true
  repo: rd8r8bkd9m-tech/kolibri-ai-platform
  private: true
  open_prs: 25
  workflow: Kolibri CI
  recent_failed_ci:
    - run_id: 28443763496
      branch: codex/kol-home-cluster-20260629-141939-009-main-codex
      conclusion: failure
servers:
  total: 20
  direct_ssh_reachable_from_mac: 2
  direct_ssh_timeout_from_mac: 18
  control_plane_cards_seen: 20
  nodes:
    - name: home
      status: online_fresh
      role: coordinator_home_mesh_control_standby
      risk: low_disk_reserve_watch
    - name: main
      status: online_fresh
      role: orchestrator_runtime
      risk: dirty_runtime_repo_and_server_github_auth
    - name: uiap
      status: online_fresh
      role: rag_knowledge_security
      risk: disk_free_0gb
    - name: qjns
      status: online_fresh
      role: tools_executor_qa
      risk: disk_free_0gb_and_clone_auth
    - name: 9fts
      status: online_fresh
      role: mesh_worker
      risk: direct_ssh_timeout_from_mac
    - name: new
      status: online_fresh
      role: review_backup_worker
      risk: direct_ssh_timeout_from_mac
    - name: primary-candidate
      status: online_fresh
      role: primary_control_standby
      risk: dirty_runtime_repo
    - name: agent-01
      status: degraded_fresh
      role: codex_mimo_worker
      risk: degraded_card
    - name: agent-02
      status: degraded_fresh
      role: codex_mimo_worker
      risk: degraded_card
    - name: agent-03
      status: degraded_fresh
      role: codex_mimo_worker
      risk: degraded_card
    - name: agent-04
      status: degraded_fresh
      role: mesh_only
      risk: no_full_resource_card
    - name: agent-05
      status: degraded_fresh
      role: mesh_only
      risk: no_full_resource_card
    - name: agent-06
      status: degraded_fresh
      role: mesh_only
      risk: no_full_resource_card
    - name: agent-07
      status: degraded_fresh
      role: mesh_only
      risk: no_full_resource_card
    - name: agent-08
      status: degraded_fresh
      role: mesh_only
      risk: no_full_resource_card
    - name: agent-09
      status: degraded_fresh
      role: mesh_only
      risk: no_full_resource_card
    - name: highload
      status: degraded_fresh
      role: mesh_only_highload
      risk: no_full_resource_card
    - name: paris
      status: degraded_fresh
      role: mesh_only_highload
      risk: no_full_resource_card
    - name: reserve242
      status: degraded_fresh
      role: mesh_only_reserve
      risk: no_full_resource_card
    - name: server-kfrm
      status: degraded_fresh
      role: mesh_only_formula_lm_candidate
      risk: no_full_resource_card
dirty_tree:
  mac_status: docs_only_untracked
  mac_subsystems:
    - docs_agent_global_intelligence
  server_dirty_runtime_repos:
    - main
    - primary-candidate
main_blockers:
  - uiap_and_qjns_disk_free_0gb
  - agent_host_generic_runner_contract_not_strict_enough
  - server_github_auth_noninteractive_clone_fetch_broken
  - direct_ssh_timeout_to_18_of_20_nodes_from_mac
  - p0_integration_audit_artifact_path_drift
  - giant_pr_46_must_be_split
completed_work:
  - mac_local_repo_branch_worktree_scan
  - github_pr_ci_issue_scan
  - control_plane_20_node_inventory
  - local_artifacts_index
  - global_intelligence_pack_created
running_work:
  - live_control_plane_and_agent_hosts
  - open_pr_ci_review_flow
blocked_work:
  - p0_integration_contract_audit
  - qjns_clone_auth_tasks
  - uiap_qjns_disk_dependent_tasks
next_tasks:
  - harden_agent_host_generic_runner_contract
  - restore_disk_reserve_uiap_qjns
  - fix_server_github_auth_without_secret_leak
  - preserve_dirty_runtime_diffs
  - split_pr_46
must_send_to_chatgpt:
  - docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/GLOBAL_DIGEST_FOR_CHATGPT.md
  - docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/SERVER_CLUSTER_READINESS.md
  - docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/ALL_BRANCHES_GLOBAL_MATRIX.md
  - docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/RISK_REGISTER.md
  - docs/agent/global-intelligence/2026-06-30-mac-server-github-full-intelligence/NEXT_DEVELOPMENT_TASKS.md
thin_client_only_policy_superseded: true
mac_development_allowed: true
server_execution_still_required_for_heavy_tasks: true
secrets_redacted: true
```
