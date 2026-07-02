# Next

Next exact task:

`P0_REPAIR_HOSTVDS_AGENT_04_GITHUB_AUTH_AND_SSH_ROUTE_2026_07_02`

Objective:
- Run on `mesh-agent-04` through Control Plane.
- Check GitHub CLI presence and auth status without printing tokens.
- Check git remote auth with non-mutating `ls-remote` only.
- Check whether direct SSH to `hostvds-agent-04` should be restored or formally replaced by Control Plane-only routing.
- Keep `push_to_main`, force push, service restart, credential creation, interactive login, and secret output forbidden.

Recommended assignment:
- `target_node=mesh-agent-04`
- `allowed_nodes=["mesh-agent-04"]`
- `kind=owner_remote_task`
- `runner=codex`
- Russian display name: `Николай - Ремонт доступа hostvds-agent-04`

