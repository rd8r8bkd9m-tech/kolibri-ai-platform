# Fleet Always Online Policy

Status: owner law for Kolibri Factory operations.

Owner rule: the factory must be kept in a working state at all times. All 20
owner servers are expected to be online, routable, observable and repairable.

## Invariant

Every canonical server must have one of these states:

- `full`: fresh heartbeat, Fabric API route, Agent Host ready, GitHub access
  classified, runner readiness classified and resource probes current.
- `partial`: reachable and useful for limited work, with explicit blockers.
- `degraded`: reachable but not safe for normal routing; repair task required.
- `unreachable`: no direct route, but fallback/API relay must create repair
  task and keep work running elsewhere.
- `stale`: old duplicate/card metadata; must not be counted as capacity.

Agents must never treat `unreachable`, `degraded` or `stale` as a dead end.
They must return structured status and create a repair action.

## Required Behavior

- Maintain a canonical list of the 20 owner servers.
- Compare canonical servers against Control Plane node cards and mesh shadows.
- Count only fresh heartbeats as working capacity.
- Keep stale cards visible as metadata debt, not server capacity.
- Route work to healthy fallback nodes while broken nodes are repaired.
- Dispatch repair tasks for broken Agent Host, GitHub auth, MIMO/API runner,
  disk, memory, VPN/mesh, DNS/firewall, Control Plane registration or service
  failures.
- Keep owner-facing status current with total servers, working servers,
  degraded servers, stale cards, active repairs and next action.

## Control Plane Guardian

Control Plane must run a guardian loop for the factory.

Responsibilities:

- poll Control Plane health, node cards, Agent Host heartbeats, queue/lease
  health and artifact completion;
- classify every canonical server and every stale/mesh duplicate card;
- detect broken servers, stuck tasks, expired leases, missing artifacts and
  runner contract violations;
- create repair task envelopes for broken nodes and route them to healthy
  repair agents;
- keep owner work moving through fallback nodes while repairs run;
- write durable artifacts and update GitHub/dispatcher ledger;
- avoid alert spam by using idempotency keys, backoff, rate limits and task
  deduplication.

No broken node should wait silently for manual discovery. If a node is broken,
the guardian records the reason, fallback route, repair task and next check.

## MIMO And Subagent Capacity

Target state:

- every canonical server should be able to host up to 20 MIMO/subagents when
  resource probes and policy allow;
- the whole factory may run up to 1000 logical agents through a scheduler;
- logical agents are not the same as OS processes: the scheduler must map them
  onto actual CPU, RAM, disk, model/API and queue capacity.

Capacity gates:

- fresh heartbeat;
- disk and memory pressure check;
- Agent Host running;
- MIMO/API runner auth classified;
- GitHub access classified;
- task artifact contract verified;
- provider/API limits respected;
- no secrets printed;
- no fake accounts, provider bypass or terms abuse.

If a node cannot safely run 20 MIMO/subagents, it must report a smaller
capacity and a repair/upgrade task.

## 24/7 Buddy Trigger And Handoff

The factory should keep running even when one command node is idle/offline.

Rules:

- command/control nodes send heartbeat and guardian status to each other;
- healthy nodes may enqueue follow-up checks and repair tasks for degraded
  nodes;
- tasks must be idempotent and deduplicated by `task_id`/`idempotency_key`;
- no infinite loops: each repeated repair uses retry limits, backoff and a
  blocker classification;
- handoff artifacts must include owner-visible state, next action and fallback
  route.

## Failure Taxonomy

Use these blocker classes:

- `api_unreachable`
- `vpn_down`
- `firewall`
- `dns`
- `disk_full`
- `memory_pressure`
- `agent_host_down`
- `control_plane_registration_stale`
- `github_auth_failed`
- `runner_auth_failed`
- `mimo_provider_denied`
- `service_failed`
- `stale_card`
- `unknown`

## Always-On Repair Loop

1. Snapshot Control Plane `/health`, `/v1/nodes`, `/v1/tasks` and filesystem
   manifests.
2. Classify each canonical server and each node card.
3. Exclude stale duplicates from capacity counts.
4. Dispatch repair tasks for degraded/unreachable canonical servers.
5. Continue owner work on fallback nodes.
6. Write artifacts and update GitHub/dispatcher ledger.
7. Recheck until every canonical server is `full` or has an active blocker with
   a repair task and owner-visible next action.

## Non-Negotiable Guardrails

- Do not print secrets.
- Do not fake healthy status.
- Do not mark a server repaired without fresh evidence.
- Do not use destructive commands for repair without explicit owner approval.
- Do not rotate credentials, restart production services or change firewall/VPN
  rules without scoped task authorization and rollback notes.
- Do not count stale cards as working servers.

## First P0 Task

`P0_FLEET_ALWAYS_ONLINE_GUARDIAN_AND_20_SERVER_RESTORE_2026_07_01`

Goal: create a remote guardian/recovery run that classifies all canonical
servers, defines the 24/7 Control Plane guardian loop, probes per-server
MIMO/subagent capacity, repairs safely where allowed, creates exact repair
backlog for every remaining blocker and updates the owner
dashboard/dispatcher ledger.
