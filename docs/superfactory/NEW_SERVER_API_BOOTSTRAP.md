# New Server API Bootstrap

## Цель

Новый сервер добавляется в Kolibri Factory через API-контракт, а не через ручную коллекцию SSH-команд.

## Bootstrap sequence

1. Register node.
2. Issue node identity.
3. Install Agent Host.
4. Join mesh/API network.
5. Expose `/v1/health`.
6. Appear in `/v1/fleet/nodes`.
7. Receive read-only test task.
8. Rotate keys by policy.
9. Become routable.

## Required endpoint

```text
POST /v1/admin/bootstrap-node
```

## Bootstrap request

```json
{
  "task_id": "string",
  "trace_id": "string",
  "owner": "Vladislav",
  "source": "mac",
  "command_node": "macbook-air-vladislav",
  "requested_role": "owner_root",
  "target_node": "new-node",
  "fallback_allowed": true,
  "write_scope": ["node_identity", "agent_host", "mesh_config"],
  "constraints": {
    "print_secrets": false,
    "destructive_actions_forbidden": true,
    "bootstrap_only": true
  }
}
```

## Acceptance for new node

- Node has stable node_id.
- Node has per-node identity.
- Node exposes health.
- Node appears in fleet topology.
- Node has Agent Host.
- Node receives and completes read-only probe.
- Node artifacts are discoverable.
- Rotation policy is recorded.
- SSH is no longer required for normal work after bootstrap.

