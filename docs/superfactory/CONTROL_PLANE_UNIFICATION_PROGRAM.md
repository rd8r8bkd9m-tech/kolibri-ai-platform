# Control Plane Unification Program

Snapshot: 2026-07-02

## Problem

Control Plane development has split into parallel lines:

- `main`: stable repository baseline.
- live primary runtime: backlog, permission packs, scheduler indexes and
  runtime stack behavior.
- standby and PR140 line: lease storm repairs, bounded queue scans, no-task
  responses, thread caps and capacity controls.
- current fleet line: Fabric API, filesystem namespace, fleet rollout memory,
  unreachable-node repair sweep and MIMO route policy.

These lines must become one production trunk. A fractal factory cannot scale if
core control logic is split across runtime-only files, PR branches and local
operator memory.

## Target

Create one unified Control Plane trunk that supports:

- Fabric API endpoints and canonical envelopes.
- Federated node registry and filesystem namespace.
- Bounded lease flow with queue indexes, no-task response and backoff.
- Backlog scheduler, permission packs and capability compatibility.
- Fleet repair sweep and always-online guardian.
- MIMO Pool Node routing instead of mass direct polling.
- Deployment canary, rollback and runtime drift detection.

## Architecture Rules

1. The repository is the source of truth. Runtime files must match a git commit
   or produce a drift alert.
2. The live runtime may teach the trunk, but must not remain an untracked fork.
3. Every Control Plane feature is contract-tested before deployment.
4. Every production deployment has a canary and rollback path.
5. The Mac remains a thin director terminal; remote agents implement and verify.
6. Local subagents are for local inspection only, not primary development.
7. Director decisions and owner escalation rules follow
   `DIRECTOR_OPERATING_CHARTER.md`.

## Workstreams

### P0 Unified Runtime Contract

Owner: remote implementation agent.

Deliverables:

- merge Fabric API, filesystem namespace, lease/capacity, scheduler/backlog and
  permission-pack behavior into one `ops/factory_control.py`;
- keep `ops/agent_host.py` compatible with no-task lease responses and runner
  capability publishing;
- add runtime drift detection comparing service file hash to git commit.

### P0 Lease And Queue Contract

Owner: remote runtime agent.

Deliverables:

- `POST /v1/tasks/lease` returns either a task with `task_id` or a structured
  no-task response;
- incompatible queued tasks do not block compatible later tasks;
- lease scans are bounded and indexed;
- expired leases are reaped through indexed active lease ids;
- Agent Host treats no-task responses as idle, not malformed tasks.

### P0 Federation And Registry Contract

Owner: remote topology agent.

Deliverables:

- canonical node identity separate from mesh shadow cards;
- hierarchy fields: `cell_id`, `parent_cell_id`, `region_id`, `domain_id`;
- state reducers for parent Control Planes;
- fallback route and repair task references for blocked nodes.

### P0 Deployment And Canary Contract

Owner: remote release agent.

Deliverables:

- canary deploy to standby first;
- smoke lease for a bounded repair task;
- promote primary only after standby passes;
- record rollback artifact and runtime hash.

## Required Tests

- black-box `/v1/tasks/lease` contract test;
- head-of-line queue test with many incompatible tasks before one compatible
  task;
- MIMO repair task compatibility test for `target_node=main`,
  `required_capability=orchestrator`, `runner=mimo`;
- no-task response handling in Agent Host;
- runtime drift detection test;
- Fabric API endpoint contract test;
- filesystem namespace redaction test;
- federation reducer test.

## Remote Delegation Policy

All workstreams must be submitted as remote task envelopes. The director may
inspect locally, stage integration branches and review results, but
implementation should run on remote factory nodes whenever the Control Plane is
healthy enough to accept tasks.

If Control Plane health blocks delegation, the director records the blocker and
creates a repair task instead of silently falling back to local implementation.
