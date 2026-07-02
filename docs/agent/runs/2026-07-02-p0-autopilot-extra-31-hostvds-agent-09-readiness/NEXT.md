# Next

Next exact task:

`P0_REPAIR_HOSTVDS_AGENT_09_FABRIC_IDENTITY_AND_SSH_ROUTE_2026_07_02`

Objective:

Repair the `hostvds-agent-09` readiness blocker by reconciling node identity and route registration:

- Decide whether `hostvds-agent-09` should be renamed/aliased to existing `agent-09` or `mesh-agent-09`, or registered as a distinct node.
- Register a fresh Factory heartbeat for the canonical node id.
- Verify `generic_implementation` and `read_only_probe` capabilities.
- Repair SSH diagnostic reachability or explicitly mark SSH unavailable with API-only fallback.
- Install or expose `gh` only if this node is expected to perform GitHub PR work, then verify auth without printing tokens.
- Re-run Fabric route checks for `hostvds-agent-09`.

Success criteria:

- `GET /v1/fleet/route?target_node=hostvds-agent-09&required_capability=generic_implementation` returns a completed route, or the control plane returns an intentional alias route to `agent-09` or `mesh-agent-09`.
- The node card contains current disk, RAM, capabilities, agent id, health, and last heartbeat.
- GitHub auth status is classified as ready or explicitly out of scope for this node.
