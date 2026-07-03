# P0 Node Health Task Heartbeat Reconcile

Goal: repair the Control Plane/NOC mismatch where `/v1/tasks/{task_id}` shows active workers with fresh task heartbeats while `/v1/nodes` shows the same node cards as stale because their node heartbeat is old.

Plan:

1. Inspect `ops/agent_host.py`, `ops/factory_control.py`, task heartbeat paths, node heartbeat paths, and NOC status normalization.
2. Implement the smallest safe Control Plane projection fix: reconcile active task heartbeat into `/v1/nodes` only when the task is non-terminal, heartbeat-fresh, and lease-unexpired.
3. Preserve original node heartbeat evidence so operators can see that the node heartbeat itself is stale.
4. Add focused regression tests for fresh task heartbeat recovery and expired task heartbeat non-recovery.
5. Run focused verification and record blockers.
