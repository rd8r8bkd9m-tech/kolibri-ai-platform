# Plan

Task id: `P0_AUTOPILOT_EXTRA_32_HOSTVDS_AGENT_10_READINESS_2026_07_02`

Agent: `Владимир - HostVDS Agent 10`

Execution node: `mesh-agent-32:agent-host-mesh-agent-32`

Goal: probe `hostvds-agent-10` readiness for factory work, API route,
GitHub auth status, disk, runner status, and repair task.

Steps:

1. Confirm this task is running under a server-side Control Plane lease.
2. Query Control Plane node registry for `hostvds-agent-10`, `agent-10`, and
   the live alias `mesh-agent-10`.
3. Probe deployed API route endpoints without direct SSH or secret output.
4. Submit a bounded read-only child probe directly to `mesh-agent-10` for
   target-local GitHub auth classification.
5. Record readiness, blockers, artifacts, and the next exact repair task.

Safety:

- No product code changes.
- No direct push, force push, or push to `main`.
- No destructive git commands.
- No secrets, env dumps, tokens, cookies, or private keys printed.
