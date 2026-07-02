# Next

Next exact task:

`P0_REPAIR_HOSTVDS_AGENT_05_LEASE_API_GITHUB_AUTH_2026_07_02`

Objective:

Repair `hostvds-agent-05` readiness without product-code changes first.

Required scope:

1. Restore or explain direct management reachability to `31.56.196.10:22`.
2. Resolve why Control Plane shows `mesh-agent-05` online but a pinned
   `read_only_probe` remains queued without `lease_owner`.
3. Reconcile canonical `agent-05` stale identity with mesh shadow
   `mesh-agent-05`.
4. Verify deployed Control Plane Fabric aliases or deploy the already-known
   route surface repair.
5. Install/verify `gh` and GitHub auth on the target without printing secrets.
6. Rerun the pinned read-only probe and require a `completed` task with
   `lease_owner=mesh-agent-05:agent-host-mesh-agent-05` and a
   `result_reference`.

Do not:

- print secrets;
- restart services without explicit repair approval;
- modify product code;
- force push;
- push to `main`;
- run destructive git commands.

