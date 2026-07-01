# Plan

Task: `P0_CONTROL_PLANE_NODE_HEALTH_FRESHNESS_GATE_2026_07_01`

Remote agent: `Иван - Control Plane Health Guardian`

Plan:

1. Reproduce the stale/online mismatch in Control Plane node status.
2. Add a focused freshness contract so stale heartbeats are not counted as fully online.
3. Mirror the same truthfulness in backend factory status, UI, and Telegram node reporting.
4. Verify the patch on a server/control node.
5. Open a GitHub draft PR through a thin-client relay if the server cannot push/open PRs.

Guardrails:

- No service restart or live deployment in this task.
- No direct push to `main`.
- No destructive git commands.
- No secrets printed.
