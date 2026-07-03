# Result

Salvage complete.

The useful prior work was preserved from commit `2e45105` on `origin/p0/node-health-task-heartbeat-reconcile-2026-07-03`.

The preserved repair changes `/v1/nodes` so node cards are reconciled with fresh active task heartbeats only when the task is active, heartbeat-fresh, and lease-unexpired. Stale node heartbeat evidence remains visible through `node_freshness`, `node_health`, and `node_heartbeat_age_seconds`, so expired or dead workers are not masked.

The current mesh11 worktree branch is `p0/node-health-artifact-salvage-relay-mesh11`, based on the prior remote repair branch. No direct `main` push and no force push were performed.

