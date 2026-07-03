# Director Rollout Plan

1. Read `ops/factory_registry.py` and this run directory before answering fleet questions.
2. Query `/v1/fleet/summary`, `/v1/fleet/nodes`, `/v1/fleet/drift` and `/v1/tasks/queue/diagnostics`.
3. Never invent node state, runner status or service ports.
4. Create repair tasks for stale/degraded/unknown records instead of deleting runtime data.
5. Trigger subagents only with task ID, envelope, expected artifacts and status contract.
6. Keep PR and CI links in task artifacts.
7. Refresh truth snapshot periodically and regenerate queue reports.
8. Promote to production only after canary endpoints and rollback path are verified.

