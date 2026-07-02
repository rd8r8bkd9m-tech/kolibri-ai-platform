# NEXT

Next exact task:

`P0_REPAIR_HOSTVDS_AGENT_07_GITHUB_CLI_AND_LOCAL_CONTROL_ALIAS_2026_07_02`

Objective:

Continue from completed child probe `P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02`. Install or expose the approved GitHub CLI/auth path for `mesh-agent-07` using only existing owner-approved credentials, without printing secrets or interactive login. Add or document the local Control Plane alias so `127.0.0.1:9101` either works or the node contract states that `10.99.0.10:9101` is canonical. Separately, restore or document the missing `/v1/fabric/route` endpoint so route checks do not rely on `/v1/nodes` plus task leasing as a proxy. Also audit why the child task reported `pushed: true` despite `no_git_push`; no-push diagnostics should not publish branches unless the envelope explicitly permits it.

Do not:

- Push to main.
- Force push.
- Run destructive git commands.
- Print secrets or raw credential output.
- Route PR-push tasks to `mesh-agent-07` until GitHub auth is proven.

Safe interim routing:

- `mesh-agent-07` may receive read-only diagnostics and light factory checks through Control Plane.
- Avoid PR publication and release gate tasks until GitHub CLI/auth is repaired and proven.
