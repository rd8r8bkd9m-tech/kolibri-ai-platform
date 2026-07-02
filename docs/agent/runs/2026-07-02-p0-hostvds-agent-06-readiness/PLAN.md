# PLAN

Task id: `P0_AUTOPILOT_EXTRA_28_HOSTVDS_AGENT_06_READINESS_2026_07_02`

Goal: probe `hostvds-agent-06` readiness for factory work from the server-side
Control Plane lease, covering remote execution path, API route, GitHub auth
status, disk, runner status, and repair task.

Scope:

- Do not modify product code.
- Do not print secrets or environment dumps.
- Do not run destructive git commands.
- Do not push to `main` or force-push.
- Use existing Control Plane/Fabric/SSH routes where available.
- Persist sanitized owner-facing artifacts only.

Probe plan:

1. Confirm the active execution node and current lease context.
2. Attempt bounded noninteractive SSH execution against `hostvds-agent-06`.
3. Check live Control Plane health and Fabric/API route readiness.
4. Inspect task board evidence for current runner lease and existing
   hostvds-agent-06 work.
5. Classify blockers and write an exact repair-task envelope.
