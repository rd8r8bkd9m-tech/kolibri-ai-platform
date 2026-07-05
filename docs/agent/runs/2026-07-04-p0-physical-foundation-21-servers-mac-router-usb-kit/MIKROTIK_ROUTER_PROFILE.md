# MIKROTIK_ROUTER_PROFILE.md

**Date:** 2026-07-04T22:20:00Z

## Profile

```json
{
  "node_id": "mikrotik-router",
  "class": "network_node",
  "role": "home_network_router|vpn_gateway|edge_route",
  "internal_ip": "10.99.99.1",
  "external_ip": "178.207.11.90",
  "control_plane_record": false,
  "agent_host": false,
  "ssh_access": "closed",
  "web_admin": "unknown",
  "wireguard_role": "gateway",
  "criticality": "high",
  "owner_approval_required_for_changes": true
}
```

## Rules
- Do not change firewall/NAT/WireGuard rules without owner approval
- Do not store secrets in repo
- Router status must be monitored as network asset, not execution node
- If router down, Home/Mac path may degrade
