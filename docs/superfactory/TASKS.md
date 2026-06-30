# Superfactory Tasks

## P0: API-First Control Fabric

Status: drafted as contract.

Goal: implement Kolibri Fabric API as the primary management path for all command nodes, servers, agents, models and fallback routes.

Required docs:

- `API_FIRST_CONTROL_FABRIC.md`
- `FULL_CONTROL_API_POLICY.md`
- `NODE_IDENTITY_AND_KEY_ROTATION.md`
- `API_FALLBACK_ROUTING_POLICY.md`
- `ANY_NODE_API_ACCESS_RUNBOOK.md`
- `NEW_SERVER_API_BOOTSTRAP.md`
- `ADMIN_API_SECURITY_GATES.md`

Implementation order:

1. Add canonical request/response schemas for Fabric API envelopes.
2. Add `GET /v1/health` as API-first alias over current health.
3. Add fleet endpoints: nodes, topology, route, capabilities.
4. Add OpenAI-compatible model/task endpoints: `/v1/models`, `/v1/responses`, `/v1/chat/completions`.
5. Add agent endpoints: task submit, status, artifacts, cancel.
6. Add admin endpoint stubs behind security gates.
7. Add fallback routing behavior and structured blocked responses.
8. Add node identity and key rotation contracts.
9. Add new server bootstrap contract.
10. Add tests for no dead-end "server unavailable" behavior.

## P0: Restore API Reachability For Timed-Out Nodes

Status: pending.

Known deferred nodes:

- `hostvds-agent-10 / 217.60.38.191`: direct SSH from Mac reports `Network is unreachable`; API route must classify with fallback and create repair task.

Expected behavior:

- Work continues through fallback nodes.
- Broken node gets a repair task.
- Owner sees structured status, not a dead end.

## P0: Replace SSH-Centric Dispatcher Habits

Status: pending.

Rules:

- SSH is bootstrap/emergency/diagnostic only.
- Factory work enters through Fabric API.
- Every task has `task_id`, `trace_id`, route, artifacts and status.
- Mac remains a thin command node.

