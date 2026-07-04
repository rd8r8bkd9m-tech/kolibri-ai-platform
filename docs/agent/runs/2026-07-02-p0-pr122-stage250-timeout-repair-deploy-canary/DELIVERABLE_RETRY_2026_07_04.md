# Deliverable Retry Evidence

Status: `passed_runtime_canary`

Task:

`REBROADCAST_P0_PR122_STAGE250_TIMEOUT_REPAIR_DEPLOY_AND_CANARY_2026_07_02-DELIVERABLE-RETRY-DELIVERABLE-RETRY-DELIVERABLE-RETRY`

Result reference:

`docs/agent/runs/2026-07-02-p0-pr122-stage250-timeout-repair-deploy-canary/DELIVERABLE_RETRY_2026_07_04.md`

Execution window:

- Started: `2026-07-04T05:49:17Z`
- Canary started: `2026-07-04T05:53:23.069116+00:00`
- Canary finished: `2026-07-04T05:53:41.553759+00:00`
- Endpoint: `http://10.99.0.2:9101`

Node and routing evidence:

- Current task lease owner: `agent-02:agent-host-agent-02`
- `agent-02` is listed in the task `allowed_nodes`.
- `/v1/fleet/route?target_node=agent-02&required_capability=generic_implementation` returned `status=ok`, `target_node=agent-02`, and `can_continue_elsewhere=true`.
- Reported fallback nodes: `agent-07`, `home`, `home-live`, `mesh-agent-18`.
- No cancellation, deletion, force-requeue, full worker wave, MIMO wave, FormulaLM wave, qjns/uiap targeting, Telegram receiver mutation, credential mutation, push to `main`, force push, hard reset, or cleanup was performed.

PR #125 evidence:

- PR URL: `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/125`
- Current head ref: `aa8f1dc304a9e6600a71dbf88179823d7eea2c40`
- Current merge ref: `7dbca54bae93ea5f66b1f5628c9e56ad9033328f`
- Current head title: `docs: add stage250 canary PR evidence`
- Underlying repair commit in the PR branch: `f152e74711ad4f08b71551502ed273885cf4551d` (`control-plane: bound lease overload admission backlog`)
- `git diff --name-status origin/main...refs/remotes/github/pr125/merge` confirms the PR merge ref changes `ops/factory_control.py`, `ops/agent_host.py`, `tests/test_factory_capacity_controls.py`, and related run artifacts.

CI/check-run status:

Fresh GitHub check-run status could not be read from this node: `gh` is not installed, no GitHub token is configured, and unauthenticated REST returned `404` for the private repository status and check-run endpoints. Runtime action was therefore grounded in authenticated Git ref fetches, PR merge-ref source checks, focused in-process lease tests, repository preflight, and live canary evidence.

Rollback/deploy boundary:

- This retry node cannot directly read `/usr/local/bin/kolibri-factory-control`, `/etc/systemd/system/kolibri-factory-control.service`, or `/var/backups/kolibri-runtime/...` locally.
- No new runtime binary or systemd unit was installed by this retry.
- The live Control Plane endpoint was already active and serving the PR #125 lease path from prior deployment work.
- The prior rollback record remains the emergency rollback reference: `/var/backups/kolibri-runtime/20260704T050348Z-REBROADCAST_P0_PR122_STAGE250_TIMEOUT_REPAIR_DEPLOY_AND_CANARY_2026_07_02-narrow`.
- Because this retry did not perform a fresh binary install, rollback was not executed.

Live pre-canary route matrix:

| Route | HTTP | ms | Bytes |
| --- | ---: | ---: | ---: |
| `/health` | 200 | 148.48 | 113 |
| `/v1/health` | 200 | 52.40 | 113 |
| `/v1/fabric/health` | 200 | 49.91 | 231 |
| `/v1/fabric/routes` | 200 | 2720.91 | 25368 |
| `/v1/fleet/nodes` | 200 | 2782.96 | 27034 |
| `/v1/models` | 200 | 27.78 | 442 |
| `/v1/tasks?limit=1` | 200 | 468.91 | 17682 |

Bounded stage canary:

Synthetic request body used `node_id=pr125-stage250-retry-20260704-agent02-no-claim`, synthetic agent ids, `capabilities=["stage250_synthetic_no_match_retry"]`, `permissions=[]`, and `runners={}`. This intentionally exercised the lease fast path without matching or claiming real queued work.

| Stage | Requests | HTTP result | Claimed tasks | Errors | 5xx | p50 ms | p95 ms | max ms | wall ms |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 20 | `204 x20` | 0 | 0 | 0 | 321.25 | 329.33 | 331.55 | 376.91 |
| 50 | 50 | `204 x50` | 0 | 0 | 0 | 498.41 | 863.84 | 947.48 | 1019.03 |
| 100 | 100 | `204 x100` | 0 | 0 | 0 | 901.52 | 1498.88 | 1610.09 | 1737.06 |
| 250 | 250 | `204 x250` | 0 | 0 | 0 | 1392.60 | 2362.07 | 2476.56 | 2827.92 |

Live post-canary route matrix:

| Route | HTTP | ms | Bytes |
| --- | ---: | ---: | ---: |
| `/health` | 200 | 130.81 | 113 |
| `/v1/health` | 200 | 81.93 | 113 |
| `/v1/fabric/health` | 200 | 81.65 | 231 |
| `/v1/fabric/routes` | 200 | 2836.56 | 27209 |
| `/v1/fleet/nodes` | 200 | 2796.62 | 26144 |
| `/v1/models` | 200 | 11.73 | 442 |
| `/v1/tasks?limit=1` | 200 | 323.82 | 17682 |

Post-canary queue state:

- `queue_length=0`
- `queue_total=0`
- `active_candidate_total=2`
- `candidate_total=2`
- No synthetic canary request returned a task id.

Checks run:

- `git fetch origin refs/pull/125/head:refs/remotes/github/pr125/head refs/pull/125/merge:refs/remotes/github/pr125/merge` passed.
- `git diff --name-status origin/main...refs/remotes/github/pr125/merge` passed.
- `python3 -m py_compile ops/factory_control.py ops/agent_host.py` passed on the deliverable branch.
- `./scripts/preflight-factory-control-runtime.sh /srv/kolibri-ai-platform` passed: `factory_control_runtime_preflight=ok`.
- `python3 -m py_compile ops/factory_control.py ops/agent_host.py` passed in a temporary detached worktree at PR #125 merge ref `7dbca54bae93ea5f66b1f5628c9e56ad9033328f`.
- In-process execution of the 12 PR-specific `tests/test_factory_capacity_controls.py` checks passed in the PR merge worktree.
- `git diff --check` passed before artifact edits.
- Required artifact file checks passed before artifact edits.
- `python3 -m pytest -q tests/test_factory_capacity_controls.py` could not run because this node has no `pytest` module and no `pip`.

Decision:

The retry canary passed. Keep this result bounded; do not use it to launch a full worker wave. Broader rollout still needs authenticated GitHub check-run visibility and an owner-approved staged runtime task on a selected healthy node.
