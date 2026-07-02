# Federated Fractal Control Plane

Snapshot: 2026-07-02

## Prime Directive

Kolibri AI must grow as a federated fractal factory, not as one central
process with an ever larger queue. A local Mac session is a thin command and
audit terminal. Real development, execution, repair and verification are
delegated to remote factory nodes through Fabric API and Control Plane
contracts.

The system must be designed for hundreds of thousands of servers from the
first architecture layer. Every local optimization must preserve horizontal
growth, vertical hierarchy, upward federation and graceful degradation.

## Fractal Unit

The repeating unit is a factory cell:

- `cell_control`: local scheduler, lease manager and state reducer.
- `cell_workers`: Agent Host, MIMO Pool Node, Codex runner, model runner or
  service-specific worker.
- `cell_registry`: node cards, capabilities, runners, health, capacity and
  namespace roots.
- `cell_queue`: local queue shards with bounded scans, idempotency and retry.
- `cell_artifacts`: append-only task results, logs, proofs and repair notes.
- `cell_replica`: summarized state exported upward and sideways.

Every bigger structure is made from cells:

- server -> cell;
- rack/provider region -> cell cluster;
- product domain -> cell cluster;
- global factory -> federation of clusters;
- owner command surface -> root intent router, not a worker host.

## Axes Of Growth

Horizontal growth:

- add more worker cells behind a pool or shard;
- route by capability, runner, cost, health, locality and queue pressure;
- never require all nodes to poll one global queue directly.

Vertical growth:

- cell controllers report to regional controllers;
- regional controllers report summarized state to root Control Plane;
- root routes objectives and policy, not every single worker loop.

Upward federation:

- any healthy control cell can become a parent for a smaller subtree;
- parent state is a reduced view: counts, leases, blockers, repair tasks,
  capacity and artifact pointers;
- parent must not need raw access to every child filesystem.

Sideways federation:

- sibling cells can relay, fail over, mirror artifacts and accept delegated
  repair tasks;
- fallback routing must preserve idempotency and audit chain.

## Non-Negotiable Contracts

1. API-first management. SSH is bootstrap, emergency and read-only diagnostic
   only.
2. No shared writable root disk. Filesystems are exposed through namespace
   manifests and artifact APIs.
3. No single global queue. Queues are sharded, indexed and leased by cell.
4. No unbounded scans. Lease, reaper, status and registry scans have hard
   limits and indexes.
5. No silent dead ends. A blocked route returns fallback nodes, `can_continue`
   status and a repair task.
6. No local-agent dependency. The Mac can inspect and direct, but remote work
   must continue when the Mac session is gone.
7. No parallel Control Plane forks without convergence. Experimental lines must
   merge into a unified trunk or be retired.
8. No secret broadcast. Credentials stay node-local or in scoped secret stores;
   state replication carries references and capabilities, not secrets.
9. No broad remote use of the Mac. Remote nodes receive scoped grants only.
10. No local token burn as a scaling strategy. The 5-hour local token window is
    budgeted and work moves remote-first under pressure.

## Control Plane Layers

Root Control Plane:

- owner intent intake;
- policy, budget, priority and safety gates;
- global topology summary;
- delegation to regional or domain controllers;
- merge/release train for Control Plane itself.

Regional or domain Control Plane:

- queue shard ownership;
- local health and capacity;
- task lease issuance;
- artifact and result aggregation;
- local repair task creation.

Cell Control Plane:

- Agent Host lifecycle;
- runner availability;
- task execution heartbeat;
- local filesystem namespace manifest;
- local artifact write path.

## Delegation Law

The director node should delegate implementation to remote agents by creating
task envelopes and submitting them through Fabric API.

Local subagents are allowed only for local Mac inspection, UI/browser work, or
fast codebase reading that cannot yet be performed through the remote fabric.
They must not become the primary execution model.

Director decisions are governed by `DIRECTOR_OPERATING_CHARTER.md`: the
director chooses safe next steps, delegates remote work and escalates to the
owner only for budget, secrets, destructive actions, production-risk decisions
or Telegram receiver changes.

Remote task envelopes must include:

- `task_id`;
- objective and acceptance criteria;
- target capability or pool;
- runner preference;
- branch and base ref;
- bounded write scope;
- verification commands;
- artifact requirements;
- fallback and repair instructions.

## State And Replication

State must be reduced before it is replicated upward:

- node counts by health and capability;
- active leases and expiring leases;
- queue depth by shard and priority;
- error taxonomy and repair task ids;
- artifact references and content hashes;
- current release train status;
- budget and provider limits.

Raw logs, local paths and secrets stay local unless an authenticated diagnostic
request asks for them. Replication is eventually consistent, but task leasing
is exclusive and idempotent.

When a remote cell lacks context, it requests a scoped grant. The director
issues only the missing information, with purpose, expiry and audit trail.

## Unified Trunk Requirement

All Control Plane lines must converge into one trunk:

- Fabric API and filesystem namespace;
- lease/capacity and empty-poll repairs;
- backlog, permission and scheduler contracts;
- fleet repair sweep and always-online guardian;
- owner-facing control panel API;
- deployment/canary/rollback runbooks.

The unified trunk is the only production promotion source. Runtime hotfixes may
exist briefly, but they must be captured as a task, tested, committed and merged
back into the trunk.
