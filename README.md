# Kolibri AI Platform

Kolibri is a remote-first AI factory: a mesh of servers, a Control Plane, and
persistent Agent Hosts that execute owner tasks outside the MacBook. The MacBook
is only a thin client for Codex, Telegram, browser checks, and emergency
bootstrap.

The repository is the shared source of truth for humans and agents. Runtime
state lives in the remote Control Plane and is reported back through Telegram in
plain Russian, without task IDs or service paths unless technical evidence is
explicitly requested.

## Current Runtime Baseline

Last verified: 2026-06-28.

| Layer | Current contract |
| --- | --- |
| Owner interface | Telegram bot and Codex thin client |
| Director/orchestrator | Persistent remote service on Primary candidate |
| Task transport | Control Plane API and Redis queue |
| Worker runtime | `kolibri-agent-host` systemd services on remote nodes |
| Mesh transport | Internal `10.99.0.0/24` network and mesh agents |
| Local MacBook role | Thin client only; no long-running factory runtime |
| Deprecated path | Direct `/api/exec`, `/task/execute`, shell-based remote exec |

Verified remote evidence:

| Check | Result |
| --- | --- |
| Control Plane health | `ok`, Redis `PONG`, queue backend `redis` |
| Primary Agent Host | `primary-candidate:agent-host-primary`, PID `539816` |
| Telegram Gateway | active on Primary, PID `541923` |
| Runtime hardening task | `KOL-RUNTIME-EXEC-HARDENING-20260628T034842Z`, completed |
| Mesh exec endpoints | `/api/exec` and `/task/execute` return `404` on mesh coordinator |
| Distributed smoke | `main`, `9fts`, `new` completed read-only probes |

## Architecture

```text
Owner
  |
  | Telegram / Codex thin client
  v
Primary candidate
  - Telegram gateway
  - Director/orchestrator voice
  - Agent Host
  |
  | Control Plane API
  v
Main / Control Plane
  - Redis queue
  - task registry
  - node registry
  - leases and heartbeats
  |
  | internal mesh 10.99.0.0/24
  v
Remote Agent Hosts
  - main
  - home
  - 9fts
  - new
  - uiap
  - qjns
  - mesh-* nodes
```

Task lifecycle:

```text
owner message
  -> Telegram Gateway
  -> Control Plane task
  -> compatible Agent Host leases task
  -> heartbeat + logs + result.json
  -> optional review/deploy/check task
  -> Telegram sends human-readable result
```

## Node Registry

The live registry is exposed by the Control Plane at `/v1/nodes`. The current
remote snapshot shows 43 registered nodes and 28 nodes with a recent heartbeat.
Not every registered node is healthy enough for writes; task scheduling must
respect drain/quarantine state.

Core nodes:

| Node ID | Hostname | Internal role | Current status |
| --- | --- | --- | --- |
| `primary-candidate` | `kolibri` | Director, Telegram gateway, Agent Host | active |
| `main` | `kolibri-main-api` | Control Plane/API gateway workload | active |
| `9fts` | `kolibri-inference-recovery` | worker/inference/research host | active |
| `new` | `kolibri-worker-backup` | worker/review/backup host | active |
| `home` | `plastilin` | home coordinator/storage candidate | draining |
| `home-live` | `plastilin` | live home registration | draining |
| `uiap` | `kolibri-rag-knowledge` | RAG/knowledge node | draining, disk constrained |
| `qjns` | `kolibri-tools-executor` | tool executor | draining, disk constrained |

Additional mesh registrations include `mesh-primary`, `mesh-main`,
`mesh-home`, `mesh-new`, `mesh-9fts`, `mesh-uiap`, `mesh-qjns`,
`mesh-agent-01` through `mesh-agent-09`, and other reserve/highload nodes.

## Remote Execution Contract

All ordinary work must go through the Control Plane, not direct SSH command
execution.

Allowed task flow:

1. Create a task through `POST /v1/tasks`.
2. Let an Agent Host lease it through `/v1/tasks/lease`.
3. Keep the lease alive with heartbeats.
4. Write logs and structured `result.json`.
5. Complete, fail, retry, or review through Control Plane endpoints.

Direct SSH is reserved for bootstrap/repair when the Control Plane or Agent Host
is unavailable. It must not become the normal task transport.

Deprecated and disabled:

- direct mesh `/api/exec`;
- direct mesh `/task/execute`;
- server-side `codex exec` as a runtime runner;
- shell-string execution for mesh tasks;
- service responses that expose worktrees, result paths, tokens, or internal IDs
  to the owner by default.

## Control Plane

`ops/factory_control.py` is the lightweight factory sidecar. It uses Redis and
stores:

- node registrations;
- node heartbeats;
- task queue;
- task leases;
- task heartbeats;
- task results;
- retry/dead-letter state;
- local spool fallback if Redis is unavailable.

Important task states:

| State | Meaning |
| --- | --- |
| `queued` | waiting for a compatible Agent Host |
| `leased` | assigned to a node |
| `running` | Agent Host is actively heartbeating |
| `waiting_review` | implementation finished but review is missing |
| `review` | independent review is running |
| `completed` | task has a structured result |
| `failed` | task failed and retry budget is exhausted |
| `dead_letter` | task cannot safely continue |

## Agent Host

`ops/agent_host.py` is the persistent worker process. It runs as a systemd
service on remote servers and reports:

- `node_id`;
- `hostname`;
- `agent_id`;
- PID;
- capabilities;
- CPU/RAM/disk;
- active task;
- heartbeat time;
- worktree;
- branch;
- log paths;
- structured result path.

Supported task kinds include:

| Kind | Purpose |
| --- | --- |
| `read_only_probe` | prove node can lease and complete a safe task |
| `runtime_exec_hardening_probe` | prove old exec paths are disabled |
| `orchestrator_chat_response` | generate the live director response for Telegram |
| `owner_remote_task` | owner-requested implementation or operations task |
| `owner_image_task` | generate and return real image artifacts |
| `review_pr` | independent review task |
| `impl_factory_smoke` | factory implementation smoke task |
| `impl_retry_error_clearance` | retry/error-state implementation task |

## Telegram Director

`ops/telegram_gateway.py` is the owner-facing gateway.

Current behavior:

- normal conversation creates `orchestrator_chat_response`;
- implementation requests create `owner_remote_task`;
- image requests create `owner_image_task`;
- intermediate technical states are hidden unless useful;
- final responses are cleaned from service metadata;
- generated images are sent as Telegram photos when an image path or URL exists.

The Telegram bot must answer like the remote director, not like an individual
worker. It should remember the development context from orchestrator memory and
the Control Plane snapshot.

## Mesh

The mesh layer is the internal network and service discovery fabric. Its role is
connectivity and coordination, not arbitrary command execution.

Current mesh contract:

- internal network first;
- public SSH only for bootstrap/repair;
- node state flows into Control Plane;
- no `/api/exec` or `/task/execute` execution endpoints;
- Agent Hosts execute typed tasks after leasing from Control Plane.

## Development And Deployment

Remote-first workflow:

1. Submit a task through Telegram or Control Plane.
2. Agent Host leases it on a healthy node.
3. Implementation happens in a per-task remote worktree.
4. Tests/checks run remotely.
5. Changes are committed by the remote task flow.
6. Review is created as a separate task.
7. Deploy/staging tasks run only after the required checks pass.

Local MacBook workflow is limited to:

- reading status;
- editing source during emergency repair;
- committing repository truth when explicitly requested;
- browser checks;
- thin-client Codex coordination.

## Verification Commands

Use these only from an authorized environment with the correct internal access.

```bash
# Control Plane health
curl -sS http://10.99.0.2:9101/health

# Nodes
curl -sS http://10.99.0.2:9101/v1/nodes

# Recent tasks
curl -sS 'http://10.99.0.2:9101/v1/tasks?limit=20'
```

Local source checks:

```bash
python3 -m py_compile \
  backend/providers.py \
  infra/network/api.py \
  infra/network/organism.py \
  ops/agent_host.py \
  ops/factory_control.py \
  ops/telegram_gateway.py

python3 -m py_compile \
  tests/test_factory_runtime.py \
  tests/test_telegram_gateway.py \
  tests/test_mesh_exec_disabled.py
```

## Repository Structure

```text
kolibri-ai-platform/
├── backend/              # API and provider routing
├── frontend/             # web/mobile frontend experiments
├── infra/
│   └── network/          # mesh API and organism bridge
├── ops/
│   ├── factory_control.py
│   ├── agent_host.py
│   ├── telegram_gateway.py
│   ├── orchestrator_memory.py
│   └── orchestrator_roster.py
├── scripts/              # deployment and training scripts
└── tests/                # runtime, Telegram, mesh, and factory tests
```

## Operational Rules

- `main` must stay protected and deployable.
- One implementation task uses one short-lived branch and one writable worktree.
- Production releases must come from version tags.
- UI changes require screenshots and visual regression evidence.
- Product, UX, calculation, data, and design decisions require owner approval.
- Incomplete features must stay behind feature flags.
- Quarantined or draining nodes must not block healthy nodes.

## License

Kolibri AI Platform.
