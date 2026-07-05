# MAC_COMMAND_NODE_PROFILE.md

**Date:** 2026-07-04T22:20:00Z

## Profile

```json
{
  "node_id": "mac-owner",
  "class": "command_node",
  "owner": "Кочуров Владислав Евгеньевич",
  "role": "owner_command_client",
  "internal_ip": "10.99.0.100",
  "external_ip": null,
  "control_plane_access": "yes",
  "github_access": "yes",
  "ssh_access_to_servers": "all 21 via SSH config",
  "can_execute_heavy_tasks": false,
  "can_dispatch_tasks": true,
  "can_collect_artifacts": true,
  "can_open_control_center": true,
  "emergency_role": "owner console"
}
```

## Responsibilities
- Send owner commands
- Open Home NOC / Web UI
- Trigger GPT Action / MCP
- Manage GitHub if needed
- Observe and approve
- NOT required for factory runtime

## Rule
Factory must continue if Mac is offline.
