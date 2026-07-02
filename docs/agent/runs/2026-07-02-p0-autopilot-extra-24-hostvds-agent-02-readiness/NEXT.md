# NEXT

Next exact task: `P0_REPAIR_HOSTVDS_AGENT_02_TARGETED_LEASE_AND_ROUTE_2026_07_02`

Objective:

Repair hostvds-agent-02 targeted execution before assigning implementation work.
The repair must prove that `allowed_nodes=["mesh-agent-02"]` leases only to
`mesh-agent-02`, restore either Fabric relay or bounded SSH access to
`hostvds-agent-02`, then run a redacted GitHub auth/clone probe without printing
tokens.

Acceptance:

- Exact task targeted to `mesh-agent-02` produces artifact/worktree paths for
  `mesh-agent-02`, not `mesh-agent-24`.
- `hostvds-agent-02` route probe succeeds through approved API relay or SSH.
- GitHub auth is classified as configured, missing, expired, network-blocked, or
  unknown without exposing credentials.
- No product code, tests, CI, secrets, main branch, force push, or destructive git
  commands are touched.
