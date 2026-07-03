# Next

Submit this exact Home-side task envelope through the Control Plane when owner
is ready to run the kiosk repair:

`docs/agent/dispatcher/envelopes/P0_HOME_KIOSK_REPAIR_REMOTE_2026_07_03.json`

Primary route:

```json
{
  "method": "POST",
  "endpoint": "/v1/fabric/route",
  "body": {
    "target_node": "home",
    "task_id": "P0_HOME_KIOSK_REPAIR_REMOTE_2026_07_03"
  }
}
```

Submit route:

```json
{
  "method": "POST",
  "endpoint": "/v1/tasks",
  "file": "docs/agent/dispatcher/envelopes/P0_HOME_KIOSK_REPAIR_REMOTE_2026_07_03.json"
}
```

Fallback route:

```json
{
  "type": "fabric_relay",
  "relay_node": "primary-candidate",
  "endpoint": "/v1/fabric/relay",
  "allowed_actions": [
    "forward the same Home-bound task",
    "classify target_node_unavailable",
    "return blocked_response_shape"
  ],
  "forbidden_actions": [
    "repair Home kiosk on the relay node",
    "run Mac-local implementation",
    "change MikroTik routes",
    "change GoMesh dataplane",
    "print secrets",
    "restart production services without owner approval"
  ]
}
```

Expected blocked response if Home cannot be reached:

```json
{
  "status": "blocked",
  "reason": "target_node_unavailable_or_home_kiosk_prerequisite_missing",
  "target_node": "home",
  "fallback_nodes": [
    "home-live",
    "primary-candidate"
  ],
  "fallback_route": {
    "type": "fabric_relay",
    "endpoint": "/v1/fabric/relay"
  },
  "repair_task": {
    "kind": "repair_fabric_route_or_home_kiosk_prerequisite",
    "target_node": "home",
    "action": "restore Home Agent Host heartbeat or install/enable missing Home display/tmux prerequisite with owner approval"
  },
  "can_continue_elsewhere": false
}
```

Next exact task id:

`P0_HOME_KIOSK_REPAIR_REMOTE_2026_07_03`
