# Plan

Task id: `P0_AUTOPILOT_EXTRA_31_HOSTVDS_AGENT_09_READINESS_2026_07_02`

Agent display name: `mesh-agent-31 - HostVDS Agent 09 Readiness Probe`

Scope:

- Confirm the task executed on a server-side worker, not a local Mac.
- Probe `hostvds-agent-09` readiness for Factory work through the Fabric API route.
- Check safe fallback reachability without printing secrets.
- Record GitHub auth/tooling status without tokens.
- Record disk and runner/service status.
- Produce a Russian owner-facing summary and exact repair task.

Non-goals:

- No product code edits.
- No credential repair or login flow.
- No service restart.
- No destructive Git commands.
- No push to `main` or force push.
