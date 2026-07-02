# NEXT

Next exact task:

`P0_REPAIR_HOSTVDS_AGENT_06_ROUTE_AUTH_DISK_RUNNER_2026_07_02`

Objective:

From a server/control node, repair or precisely classify `hostvds-agent-06`
readiness without printing secrets. Restore a working noninteractive route or
Fabric relay to `hostvds-agent-06`; then run bounded checks for hostname,
UTC time, root disk usage, `kolibri-agent-host.service`,
`kolibri-factory-control.service`, `kolibri-mesh-control-bridge.service`,
noninteractive GitHub auth status, repository presence, and Agent Host runner
process status. If SSH remains unreachable, classify the network/firewall/VPN
blocker and update the Fabric route/repair task evidence.

Required acceptance:

- Execution happens from a server-side Control Plane worker, not from Mac.
- No secrets, tokens, private keys, or environment dumps are printed.
- No destructive git commands, no force push, and no push to `main`.
- Result includes target node, agent name, disk, GitHub auth status, runner
  status, API route status, blockers, artifacts, and Russian owner summary.
- If repair is not safely possible, return a precise blocker and fallback route.

Suggested route:

1. Deploy or restart the checked-in Control Plane that contains
   `/v1/fleet/route`, `/v1/fabric/routes`, and `/v1/fabric/health`, or identify
   the authoritative listener if another process owns `10.99.0.2:9101`.
2. Restore connectivity to `hostvds-agent-06` through approved SSH/Fabric relay.
3. Run the bounded target probe and persist sanitized readiness artifacts.
