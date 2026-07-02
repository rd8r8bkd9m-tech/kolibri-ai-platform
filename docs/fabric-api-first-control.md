# Kolibri API-First Full-Control Fabric

The primary management path for Kolibri factory operations is the protected Fabric API. Command nodes, the Control Plane, Agent Hosts, remote agents, model nodes, and artifact stores must be represented through direct Fabric API routes or fallback Fabric API relay routes.

SSH is not a management plane. SSH is allowed only for bootstrap, emergency recovery, and diagnostics when the Fabric API path is unavailable or not yet installed. Routine task submission, node status, relay, drain, cancellation, artifact lookup, bootstrap requests, and owner control actions must use API contracts.

## Required Fabric API Endpoints

These endpoints are implemented in `ops/factory_control.py`. Privileged operations that are not safe to execute locally are represented by safe stubs that return contracts and next actions without returning secrets.

| Endpoint | Purpose | Implementation level |
| --- | --- | --- |
| `GET /v1/fabric/health` | Report Fabric API health and primary management path. | Implemented |
| `GET /v1/fabric/policy` | Return owner rights, authz, scoping, logging, SSH policy, identity and bootstrap policy. | Implemented |
| `GET /v1/fabric/routes` | Represent every known server through direct API or fallback relay metadata. | Implemented |
| `POST /v1/fabric/route` | Resolve a direct route to a node or return structured blocked status with fallback and repair task. | Implemented |
| `POST /v1/fabric/relay` | Safe relay contract for continuing through another Fabric API node. | Safe stub |
| `POST /v1/fabric/bootstrap` | New server bootstrap contract without printing or returning credentials. | Safe stub |
| `GET /v1/fabric/keys/rotation` | Node identity and key rotation policy. | Implemented |
| `GET /v1/filesystem` | Read-only deployed file metadata for integrity and namespace checks. | Implemented |
| `GET /v1/fleet/registry/hygiene` | Read-only fleet registry hygiene and namespace drift report. | Implemented |
| `GET /v1/nodes`, `POST /v1/nodes/register`, `POST /v1/nodes/{node_id}/heartbeat`, `POST /v1/nodes/{node_id}/drain` | Agent Host identity, liveness, and operational state. | Implemented |
| `POST /v1/tasks`, `POST /v1/tasks/lease`, `POST /v1/tasks/{task_id}/heartbeat`, `POST /v1/tasks/{task_id}/complete`, `POST /v1/tasks/{task_id}/fail`, `POST /v1/tasks/{task_id}/cancel` | API-first task control. | Implemented |

## Fleet Representation

Every known server has a Fabric representation:

| Node | Display name | Role | API route |
| --- | --- | --- | --- |
| `home` | `Связной` | command node gateway | direct Fabric API or fallback relay |
| `main` | `Директор` | Control Plane | direct Fabric API |
| `uiap` | `Знания` | knowledge/model node | direct Fabric API or fallback relay |
| `qjns` | `Тестировщик` | remote agent | Agent Host API or fallback relay |
| `9fts` | `Инженер` | implementation/model node | Agent Host API, model API, or fallback relay |
| `new` | `Ревьюер` | review agent | Agent Host API or fallback relay |

Registered node heartbeats override catalog metadata, but SSH remains marked `emergency_bootstrap_diagnostic_only` in API responses.

## Blocked Envelope

Agents and command nodes must not stop at plain text such as `server unavailable`. When a direct route fails, return this JSON shape:

```json
{
  "status": "blocked",
  "reason": "target_node_unavailable",
  "target_node": "9fts",
  "fallback_nodes": ["new"],
  "fallback_route": {"type": "fabric_relay", "endpoint": "/v1/fabric/relay"},
  "repair_task": {
    "kind": "repair_fabric_route",
    "target_node": "9fts",
    "action": "register node heartbeat, clear drain state, or choose a fallback node via Fabric API"
  },
  "can_continue_elsewhere": true
}
```

The dispatcher also emits this style of envelope when the Control Plane API is unreachable.

## Owner Rights Policy

Full owner control exists as API policy, not as unauthenticated shell access. Owner actions require:

- Authentication.
- Authorization.
- Scoped permissions per command.
- Audit logging with actor, scope, node, request id, and outcome.
- Credential rotation.

The API policy includes fleet read, route, task submit/cancel, node drain, artifact read, and bootstrap create rights. Tokens and private keys must never be printed, logged, or returned by the API.

## Node Identity And Rotation

Each node has a stable non-secret `node_id`, an `agent_id` for the running process, and a Russian display name for owner-facing reports. Credentials rotate on new bootstrap, suspected compromise, owner request, node reimage, and at least every 90 days. Any overlap window must be short, audited, and used only for draining old credentials.

## New Server Bootstrap Contract

`POST /v1/fabric/bootstrap` accepts non-secret metadata:

```json
{
  "node_id": "node-name",
  "role": "remote_agent",
  "display_name": "Инженер",
  "capabilities": ["implementation"],
  "requested_by": "owner-api-identity"
}
```

The safe stub returns accepted bootstrap metadata, `secrets_returned: false`, and the next API action. Installation of privileged credentials must happen through authenticated, scoped, logged Fabric API flows.

## Remote Result Report Contract

Remote results should include:

- `task_id`.
- `node_id`.
- Russian agent display name.
- `branch` and PR URL or PR status.
- Verification commands and outcomes.
- Artifact paths and manifest paths.
- Blockers.
- Next action.
