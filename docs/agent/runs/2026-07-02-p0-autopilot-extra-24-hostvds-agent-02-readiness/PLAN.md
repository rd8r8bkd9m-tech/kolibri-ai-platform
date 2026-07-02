# PLAN

Task: `P0_AUTOPILOT_EXTRA_24_HOSTVDS_AGENT_02_READINESS_2026_07_02`

Scope: read-only readiness probe for `hostvds-agent-02` aliases
`agent-02` / `mesh-agent-02` / `kolibri-frontend-design`.

Plan:

1. Submit a Control Plane task targeted only to `mesh-agent-02`.
2. Verify whether the task is leased to the assigned node.
3. Query the Control Plane node card for `agent-02` and `mesh-agent-02`.
4. Attempt a bounded, non-interactive SSH identity probe to `hostvds-agent-02`.
5. Classify API route, disk, runner, GitHub auth status, blockers, artifacts,
   and the next exact repair task.

Constraints honored: no product code changes, no secret printing, no git push,
no force push, no push to main, no destructive git commands.
