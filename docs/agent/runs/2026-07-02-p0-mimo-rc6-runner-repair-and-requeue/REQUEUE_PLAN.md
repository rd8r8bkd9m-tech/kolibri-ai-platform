# MIMO rc=6 Runner Repair And Requeue Plan

Date: 2026-07-02

## Classification

Recent MIMO failures for home heartbeat/kiosk repair, revenue financing fallback, and free VPS research fallback are runner invocation failures, not missing artifact contract failures.

Evidence:

- `P0_HOME_AGENT_HEARTBEAT_LEASE_REPAIR_FOR_KIOSK_2026_07_02`: MIMO exited with `rc=6`; stderr reports `Network request failed` and recommends checking network/proxy.
- `P0_HOME_KIOSK_ROUTE_UNBLOCK_MIMO_RETRY_2026_07_02`: MIMO exited with `rc=6` on both attempts before producing outputs.
- `P0_REVENUE_FINANCING_ANALYZER_FALLBACK_MESH_2026_07_02`: MIMO exited with `rc=6`; stderr reports the same network/proxy failure.
- `P0_REVENUE_FINANCING_ANALYZER_SECOND_FALLBACK_2026_07_02`: same MIMO `rc=6` runner invocation failure.
- `P0_FREE_VPS_VDS_GLOBAL_RESEARCH_FALLBACK_MESH_2026_07_02`: same MIMO `rc=6` runner invocation failure.
- `P0_FREE_VPS_VDS_GLOBAL_RESEARCH_AND_EPHEMERAL_WORKER_DESIGN_2026_07_02`: same MIMO `rc=6` runner invocation failure.

Tasks that ran with Codex and ended as `required_artifacts_missing` should be treated as output contract/prompt mismatch or incomplete artifact production, not MIMO runner failure. Examples include `P0_REVENUE_CRM_PIPELINE_SCHEMA_2026_07_02`, `P0_FREE_VPS_EPHEMERAL_WORKER_FLEET_RESEARCH_2026_07_02`, and `P1_REMOTE_MIMO_POOL_NODE_BOOTSTRAP_AND_DIRECTOR_INTEGRATION_2026_07_02`.

## Safe Requeue Rules

- Do not restart live services as part of requeue.
- Prefer `runner:codex` on online nodes for the immediate requeue wave.
- Use fixed MIMO only after a canary proves rc=6 is classified as `runner_contract_blocked` with stderr/log artifacts and without `required_artifacts_missing`.
- Keep required artifact paths exact and include `use_clean_remote_worktree: true` for repo-writing tasks.
- Route away from nodes whose last MIMO attempt failed with rc=6 until network/proxy access is repaired.

## Envelopes

### Home heartbeat/kiosk repair via Codex

```json
{
  "task_id": "P0_HOME_HEARTBEAT_KIOSK_REPAIR_REQUEUE_CODEX_2026_07_02",
  "kind": "owner_remote_task",
  "priority": "P0",
  "required_capability": "generic_implementation",
  "runner": "codex",
  "use_clean_remote_worktree": true,
  "branch": "p0/home-heartbeat-kiosk-repair-requeue-2026-07-02",
  "base_ref": "origin/main",
  "avoid_nodes": ["mesh-agent-06"],
  "objective": "Remote-only. Requeue the home heartbeat/kiosk repair work that failed before output because MIMO exited rc=6. Do not restart live services. Inspect prior artifacts, produce exact run docs, and if code changes are needed open or update a draft PR only.",
  "required_artifacts": [
    "docs/agent/runs/2026-07-02-p0-home-heartbeat-kiosk-repair-requeue/PLAN.md",
    "docs/agent/runs/2026-07-02-p0-home-heartbeat-kiosk-repair-requeue/ACTIONS.md",
    "docs/agent/runs/2026-07-02-p0-home-heartbeat-kiosk-repair-requeue/TESTS.md",
    "docs/agent/runs/2026-07-02-p0-home-heartbeat-kiosk-repair-requeue/RESULT.md",
    "docs/agent/runs/2026-07-02-p0-home-heartbeat-kiosk-repair-requeue/NEXT.md",
    "docs/agent/runs/2026-07-02-p0-home-heartbeat-kiosk-repair-requeue/ROLLBACK.md"
  ]
}
```

### Revenue financing fallback via Codex

```json
{
  "task_id": "P0_REVENUE_FINANCING_ANALYZER_REQUEUE_CODEX_2026_07_02",
  "kind": "owner_remote_task",
  "priority": "P0",
  "required_capability": "generic_implementation",
  "runner": "codex",
  "use_clean_remote_worktree": true,
  "branch": "p0/revenue-financing-analyzer-requeue-2026-07-02",
  "base_ref": "origin/main",
  "avoid_nodes": ["mesh-agent-11", "mesh-agent-13"],
  "objective": "Remote-only. Requeue the revenue financing analyzer fallback work that failed because MIMO exited rc=6 before output. Produce exact revenue plan artifacts and run docs. No live service restarts.",
  "required_artifacts": [
    "docs/agent/runs/2026-07-02-p0-revenue-financing-analyzer-requeue/PLAN.md",
    "docs/agent/runs/2026-07-02-p0-revenue-financing-analyzer-requeue/ACTIONS.md",
    "docs/agent/runs/2026-07-02-p0-revenue-financing-analyzer-requeue/TESTS.md",
    "docs/agent/runs/2026-07-02-p0-revenue-financing-analyzer-requeue/RESULT.md",
    "docs/agent/runs/2026-07-02-p0-revenue-financing-analyzer-requeue/NEXT.md",
    "docs/business/2026-07-02-kolibri-ai-financing-requeue/FAST_REVENUE_PLAN.md",
    "docs/business/2026-07-02-kolibri-ai-financing-requeue/OFFERS_AND_PRICING.md",
    "docs/business/2026-07-02-kolibri-ai-financing-requeue/NEXT_REMOTE_TASKS.md"
  ]
}
```

### Free VPS research fallback via Codex

```json
{
  "task_id": "P0_FREE_VPS_RESEARCH_REQUEUE_CODEX_2026_07_02",
  "kind": "owner_remote_task",
  "priority": "P0",
  "required_capability": "generic_implementation",
  "runner": "codex",
  "use_clean_remote_worktree": true,
  "branch": "p0/free-vps-research-requeue-2026-07-02",
  "base_ref": "origin/main",
  "avoid_nodes": ["mesh-agent-10", "mesh-agent-12"],
  "objective": "Remote-only. Requeue the free VPS/VDS global research and ephemeral worker design work that failed because MIMO exited rc=6 before output. Produce exact research and run artifacts. Do not register new workers or mutate live services.",
  "required_artifacts": [
    "docs/agent/runs/2026-07-02-p0-free-vps-research-requeue/PLAN.md",
    "docs/agent/runs/2026-07-02-p0-free-vps-research-requeue/ACTIONS.md",
    "docs/agent/runs/2026-07-02-p0-free-vps-research-requeue/TESTS.md",
    "docs/agent/runs/2026-07-02-p0-free-vps-research-requeue/RESULT.md",
    "docs/agent/runs/2026-07-02-p0-free-vps-research-requeue/NEXT.md",
    "docs/infrastructure/free-vps-workers/2026-07-02-requeue/PROVIDER_MATRIX.md",
    "docs/infrastructure/free-vps-workers/2026-07-02-requeue/EPHEMERAL_WORKER_ARCHITECTURE.md",
    "docs/infrastructure/free-vps-workers/2026-07-02-requeue/SECURITY_AND_COST_GUARDS.md",
    "docs/infrastructure/free-vps-workers/2026-07-02-requeue/ONBOARDING_PLAYBOOK.md"
  ]
}
```

### Fixed MIMO canary

```json
{
  "task_id": "P0_MIMO_RC6_CLASSIFICATION_CANARY_2026_07_02",
  "kind": "owner_remote_task",
  "priority": "P0",
  "required_capability": "runner:mimo",
  "runner": "mimo",
  "objective": "Remote-only canary after Agent Host rc=6 classifier rollout. Run a minimal MIMO prompt. If MIMO exits rc=6, result must be blocked as runner_contract_blocked with stderr_tail and runner_artifacts, and must not report required_artifacts_missing.",
  "required_artifacts": []
}
```
