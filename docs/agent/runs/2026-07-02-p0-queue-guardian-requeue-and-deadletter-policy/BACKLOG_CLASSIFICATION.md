# Backlog Classification

Task id: `P0_QUEUE_GUARDIAN_REQUEUE_AND_DEADLETTER_POLICY_2026_07_02`

Status: `completed`

Lease owner: `mesh-agent-04:autonomous_engineer`

Source:

- Checked-in dispatcher queue: `docs/agent/dispatcher/QUEUE.md`
- Runtime Redis was not mutated.

Current backlog classes from the checked-in queue:

| Class | Task ids | Policy |
| --- | --- | --- |
| `queued` | `P0_FLEET_ALWAYS_ONLINE_GUARDIAN_AND_20_SERVER_RESTORE_2026_07_01`, `P0_HOME_FACTORY_TERMINAL_UI_RU_2026_07_01`, `P0_GITHUB_ALWAYS_CURRENT_CONTRACT_2026_07_01` | Lease to compatible Agent Host. Do not bulk requeue without owner gate. |
| `running` | `P0_FACTORY_CONTROL_RUNTIME_IMPORT_PATH_REPAIR_2026_07_02`, `P0_POST_MERGE_CANARY_AND_PR_QUEUE_DRAIN_2026_07_01`, `P0_AI_RUNNER_AUTH_AND_OWNER_REMOTE_TASK_ROUTING_DIAGNOSTIC_2026_07_01` | Monitor lease owner and heartbeat. Do not cancel running tasks without owner gate. |
| `failed useful` | `P0_REPAIR_POST_MERGE_CANARY_RUNTIME_BLOCKERS_2026_07_02`, `P0_POST_MERGE_REMOTE_CANARY_EXECUTION_2026_07_02`, `P0_PR85_MINOR_DOCS_WHITESPACE_AND_MAIN_UPDATE_2026_07_01`, `P0_CONTROL_PLANE_NODE_HEALTH_FRESHNESS_GATE_2026_07_01`, `P0_GITHUB_RELEASE_STEWARD_PR_QUEUE_DRAIN_2026_07_01` | Prefer artifact relay, exact artifact repair, or targeted superseding task. Do not broad retry verifier failures. |
| `dead_letter` | `P0_DEPLOY_FACTORY_CONTROL_AND_TELEGRAM_GATEWAY_CANARY_REPAIR_2026_07_02` | Do not auto-requeue. Owner-approved replacement or targeted repair only. |
| `blocked` | `P0_QJNS_FULL_RUNNER_RESTORE_2026_07_01` | Owner/provider credential gate before retry. |

First repair queue:

1. `P0_FACTORY_CONTROL_RUNTIME_IMPORT_PATH_REPAIR_2026_07_02` - running repair for the live Factory Control import/runtime packaging blocker; let it finish or inspect lease before any supersede.
2. `P0_DEPLOY_FACTORY_CONTROL_AND_TELEGRAM_GATEWAY_CANARY_REPAIR_2026_07_02` - dead_letter deploy rollback case; prepare owner-approved replacement only after import path repair lands.
3. `P0_POST_MERGE_CANARY_AND_PR_QUEUE_DRAIN_2026_07_01` - running release steward; monitor for artifacts before duplicate dispatch.
4. `P0_FLEET_ALWAYS_ONLINE_GUARDIAN_AND_20_SERVER_RESTORE_2026_07_01` - queued fleet guardian; lease normally after higher-risk runtime repair.
5. `P0_HOME_FACTORY_TERMINAL_UI_RU_2026_07_01` - queued observability task; safe to lease after runtime blockers.

Blockers:

- Live Redis lease metadata was not queried by this repository-only run.
- Broad queue mutation remains owner-gated by policy.

Next action:

- Use the new `GET /v1/tasks/backlog/guardian` endpoint on the deployed Factory Control service for live Redis-backed classification before mutation.
