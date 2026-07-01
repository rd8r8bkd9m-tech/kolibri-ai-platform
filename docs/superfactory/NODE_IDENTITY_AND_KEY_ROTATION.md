# Node Identity And Key Rotation

## Цель

Каждый сервер, агент, command node и model node должен иметь собственную identity. Фабрика не должна зависеть от одного вечного общего ключа.

## Identity layers

| Layer | Identity |
| --- | --- |
| Node | node_id, hostname, role, capabilities, public key/cert fingerprint. |
| Agent Host | agent_host_id, service token/cert, artifact root, work root. |
| Command Node | command_node_id, owner binding, source kind. |
| Owner Session | short-lived admin token, trace_id, task_id. |
| Emergency | break-glass token/cert with strict logging and expiry. |

## Token policy

- Node tokens are scoped to one node identity.
- Owner/admin tokens are short-lived.
- Service tokens are rotated by API.
- Emergency tokens expire and trigger incident report.
- Tokens are never printed in logs, terminal summaries or artifacts.
- Rotation events are linked to `task_id` and `trace_id`.

## Required rotation endpoint

```text
POST /v1/admin/rotate-keys
```

Request must include:

```json
{
  "task_id": "string",
  "trace_id": "string",
  "owner": "Vladislav",
  "source": "mac|primorye|home|telegram|main|primary-candidate|github",
  "command_node": "string",
  "requested_role": "owner_root",
  "target_node": "string",
  "fallback_allowed": true,
  "write_scope": ["identity", "agent_host_config"],
  "constraints": {
    "print_secrets": false,
    "preserve_old_identity_until_verified": true
  }
}
```

## Rotation sequence

1. Create replacement node identity.
2. Register pending identity in Control Plane.
3. Install on target node without printing secrets.
4. Verify `/v1/health`.
5. Verify `/v1/fleet/nodes`.
6. Submit read-only test task.
7. Promote new identity.
8. Revoke old identity.
9. Write audit artifact.
