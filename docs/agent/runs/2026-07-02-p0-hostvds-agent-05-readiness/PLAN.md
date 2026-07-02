# Plan

Task id: `P0_AUTOPILOT_EXTRA_27_HOSTVDS_AGENT_05_READINESS_2026_07_02`

Executor: server-side logical worker `mesh-agent-27` on host `kolibri`.

Target readiness node: `hostvds-agent-05`, represented in Control Plane as
`mesh-agent-05` with `mesh_source_node_id=agent-05` and
`mesh_ip=31.56.196.10`.

Steps:

1. Prove this work is running from the server-side factory worker, not a local
   Mac product-code edit.
2. Probe direct SSH reachability to `hostvds-agent-05` without printing
   credentials or environment variables.
3. Query Control Plane health, task API route, and node inventory for
   `agent-05` and `mesh-agent-05`.
4. Submit a pinned read-only Control Plane task to `mesh-agent-05`.
5. Classify factory-work readiness, API route readiness, GitHub auth/tooling,
   disk, runner status, blockers, artifacts, and next exact repair task.
6. Write owner-facing Russian summary and canonical run artifacts.

Safety constraints:

- No product code changes.
- No secret printing.
- No destructive git commands.
- No force push.
- No push to `main`.
- No service restart.

