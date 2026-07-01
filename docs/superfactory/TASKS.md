# Superfactory Tasks

## P0: Fleet Always Online Guardian

Status: owner law drafted; remote guardian task required.

Goal: keep all 20 owner servers in a working state. Every server must be either
fully online and routable through Fabric API / Control Plane, or have a
structured blocker, fallback route and active repair task.

Control Plane must act as the guardian: it checks the factory, dispatches repair
commands to agents, keeps fallback execution running and maintains owner-visible
state. This must become a 24/7 loop, not a one-time audit.

Required docs:

- `FLEET_ALWAYS_ONLINE_POLICY.md`

Required behavior:

1. Maintain canonical list of the 20 owner servers.
2. Count fresh heartbeats separately from stale/mesh duplicate cards.
3. Route work only to healthy capacity.
4. Dispatch repair tasks for degraded, unreachable or stale canonical servers.
5. Keep owner-visible fleet status current.
6. Never claim "server unavailable" as a dead end.
7. Define per-server MIMO/subagent target: up to 20 MIMO/subagents per server
   when capacity allows.
8. Define logical-agent scheduler target: up to 1000 logical agents across the
   factory, constrained by measured throughput and safety gates.
9. Add buddy-trigger/handoff policy so healthy nodes keep checks and repairs
   running 24/7.

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
