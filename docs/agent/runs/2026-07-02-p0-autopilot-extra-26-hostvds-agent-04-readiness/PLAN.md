# Plan

Task: `P0_AUTOPILOT_EXTRA_26_HOSTVDS_AGENT_04_READINESS_2026_07_02`

Scope:
- Probe `hostvds-agent-04` through its live Control Plane node card `mesh-agent-04`.
- Confirm that execution can happen on the assigned server-side mesh worker.
- Record readiness for factory work, API route, GitHub auth status, disk, runner status, blockers, artifacts, and next exact repair task.
- Do not modify product code, tests, CI, service configuration, secrets, main, or PR state.

Method:
- Attempt bounded direct SSH status probe with non-interactive public-key auth.
- Use Control Plane when SSH is unavailable.
- Submit a pinned `read_only_probe` with `target_node=mesh-agent-04` and `allowed_nodes=["mesh-agent-04"]`.
- Collect sanitized task and node-card evidence.
- Produce docs-only artifacts.

