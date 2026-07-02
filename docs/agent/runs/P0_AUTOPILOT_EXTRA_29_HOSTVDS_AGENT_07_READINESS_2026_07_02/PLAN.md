# PLAN

Task: `P0_AUTOPILOT_EXTRA_29_HOSTVDS_AGENT_07_READINESS_2026_07_02`.

Goal: probe hostvds-agent-07 readiness for factory work without local Mac implementation, secret exposure, destructive git commands, force push, or push to main.

Plan:

1. Confirm this task is running under a server-side Control Plane lease.
2. Read the current Control Plane node card for `agent-07` and `mesh-agent-07`.
3. Probe the Fabric/API route for `mesh-agent-07`.
4. Try the documented SSH alias only as a bounded diagnostic.
5. Dispatch a direct read-only child probe to `mesh-agent-07` for node-local GitHub auth and runner status.
6. Record status, blockers, artifacts, and the next exact task in Russian for the owner.

Scope:

- Documentation/run artifacts only.
- No product code changes.
- No secret printing.
- No destructive git commands.
