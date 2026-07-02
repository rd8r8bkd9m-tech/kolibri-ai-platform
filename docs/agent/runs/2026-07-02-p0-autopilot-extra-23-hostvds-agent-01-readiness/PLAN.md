# Plan

Task: `P0_AUTOPILOT_EXTRA_23_HOSTVDS_AGENT_01_READINESS_2026_07_02`

Goal: probe hostvds-agent-01 readiness for factory work, API route/control-plane reachability, GitHub auth status, disk, runner status, and repair task without modifying product code or printing secrets.

Steps:

1. Inspect the dispatcher/runtime contracts and prior remote-result artifacts.
2. Query Control Plane nodes for `agent-01`, `mesh-agent-01`, and the active lease worker.
3. Submit a bounded read-only `owner_remote_task` envelope targeted only at `mesh-agent-01`.
4. Poll exact task status and node cards.
5. Record readiness facts, blockers, artifacts, and the next exact task.

Safety constraints:

- No product code changes.
- No destructive git commands.
- No force push or push to `main`.
- No credential repair, token refresh, interactive login, or secret output.
- Russian owner-facing summary required.
