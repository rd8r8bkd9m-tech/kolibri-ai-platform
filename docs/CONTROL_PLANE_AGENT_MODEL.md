# Control Plane and Agent execution model

Status: Home-first implementation contract, 2026-07-12. This document
separates the reviewed Python compatibility runtime from the required Kolibri
AI OS target. It does not claim that a strict Home canary, a signed rollout or
a 21-node execution campaign has passed.

Normative details live in:

- `docs/agent/AGENT_RUNNER_CONTRACT.md` for the runner boundary;
- `contracts/kolibri-os-v1/control-plane.schema.json` for compatibility task,
  lease, fence, heartbeat and completion records;
- `contracts/kolibri-os-v1/openapi.json` for the public HTTP surface and its
  `x-kolibri-implementation` status;
- `docs/CONTROL_PLANE_HOME_CANONICAL.md` for Home-only authority;
- `docs/KOLIBRI_OS_V1_CONTRACT_FREEZE.md` for the product-wide target.

This page explains those contracts. It is not a second endpoint specification.

## Authority and plane separation

```text
Owner / Shell / API client
            |
            v
Unified Kolibri API
            |
            v
control-plane/home
  task state, attempts, leases, fences, policy, verifier truth
            |
            | API-only worker lifecycle
            v
Execution Plane
  Agent Hosts -> Mimo / Codex / tools / local models / builds
            |
            v
result bytes + hashes + provenance -> independent Home verifier
```

`control-plane/home` is the only logical task authority. Hostnames and IP
addresses are discovery metadata. Historical `main`, `primary` and
`primary-candidate` identities are not scheduler or release fallbacks and may
participate only as ordinary workers after the same gates as any other node.

The Control Plane schedules, leases, fences and verifies work. It does not run
provider inference or builds. Workers register, lease, heartbeat, complete and
fail through API contracts. SSH is operator-only bootstrap, diagnostics and
emergency recovery; it is never worker transport.

Provider selection is independent of task authority. Mimo, Codex, specialized
APIs and local models are Execution Plane routes beneath Home. A provider
failure can change the provider route, but it cannot change the Control Plane.
The public model identity remains `kolibri`.

## Current compatibility versus required target

| Concern | Reviewed compatibility source | Required target and release gate |
| --- | --- | --- |
| Task authority | `ops/factory_control.py`, Home-only, fail-closed | Rust authority with a positive quorum-issued `authority_epoch`; stale leaders cannot mutate state |
| Task persistence | Redis compatibility state | PostgreSQL Program Ledger plus transactional outbox/inbox |
| Dispatch/events | Redis queue and compatibility HTTP routes | NATS JetStream mailboxes and durable ordered events |
| Lease safety | Home-issued `attempt_id`, `lease_owner` and monotonic positive `fencing_token` | Same binding plus positive `authority_epoch` on every mutation |
| Completion truth | Home recomputes result and binding hashes and persists an independent verifier | Same verifier plus CAS-bound required artifacts and epoch binding |
| Agent concurrency | Python Agent Host is a single-slot compatibility worker and publishes scalar `active_task` | Rust multi-slot supervisor with bounded physical slots and exact `active_attempts` |
| Artifacts | Node-local result path and file manifest are compatibility evidence | Immutable content-addressed storage with bytes, MIME, size, SHA-256 and verifier binding |
| Fleet evidence | Signed mesh membership and heartbeat freshness are separate observations | Per-release capability proof for every canonical node; aggregate readiness derives only from verified attempts |

The Python source contains the strict fencing and completion-verifier logic,
but source presence is not live proof. The digest-bound Home compatibility
bootstrap may update only the reviewed Factory Control entrypoint after the
Agent Runner/OpenAPI contract freeze. A side-by-side canary and post-restart
contract checks must pass before the installed runtime can be called strict.

The compatibility runtime does not yet persist or validate `authority_epoch`,
does not materialize artifacts into durable CAS and does not provide multi-slot
Agent Host execution. Those gaps remain `partial`; documentation, a process,
an HTTP `200` or a heartbeat cannot promote them to ready.

## Task, attempt, lease and fence

A task is the durable unit of intent. It contains an idempotency key, objective,
acceptance assertions, required capabilities/resources, attempt budget,
permissions/write scope, artifact requirements, verifier policy and provenance.
`max_attempts` is canonical and counts the first attempt. `max_retries` is a
read-only two-wave input alias; new producers never emit it.

An attempt is one fenced execution of that task. Home assigns:

```json
{
  "attempt_id": "task-123-attempt-2",
  "lease_owner": "node-id:agent-id",
  "lease_until": 1783891200.0,
  "fencing_token": 7
}
```

The required target also includes the current positive `authority_epoch`.
Workers never invent or increment these fields.

Lifecycle rules:

1. An idempotent task enters `queued` with fencing schema
   `kolibri.lease-fencing.v1` and token zero.
2. A successful lease creates a new `attempt_id`, binds
   `lease_owner=node_id:agent_id`, sets `lease_until` and increments the token
   to a positive value.
3. Task heartbeat, completion and failure must repeat the matching attempt,
   node, agent and fence. The target contract also repeats the authority epoch.
4. Heartbeat extends only the matching live lease. It proves liveness, not
   completion or provider capability.
5. A late attempt, wrong owner, stale fence or stale epoch returns HTTP `409`.
   Its output may be quarantined as evidence but cannot change task state.
6. Lease loss consumes one attempt. Retry creates a new attempt with a strictly
   larger fence only while `attempt < max_attempts`; otherwise the task becomes
   `dead_letter`.
7. Cancellation revokes the live lease. Client disconnect alone does not
   cancel durable work.

## Completion and verifier truth

The worker may request completion only after its local runner contract passes.
The request binds a non-empty canonical result and result reference to the
current task, attempt, node, agent and fence. Home independently canonicalizes
the result and recomputes:

```text
result_sha256 = SHA-256(canonical JSON result)
binding_sha256 = SHA-256(
  schema + task_id + attempt_id + lease_owner + fencing_token
  + result_reference + result_sha256
)
```

The required target includes `authority_epoch` in that binding. Home persists:

- `kolibri.task-completion-evidence.v1`;
- `kolibri.task-completion-binding.v1`;
- `kolibri.control-plane-completion-verifier.v1` with
  `verifier=control-plane/home`, `independent=true` and `verdict=passed`.

`completed` is allowed only when every check recomputes successfully. A stored
`verdict=passed`, provider reply, local file name, log line or runner-reported
status is not trusted on its own. Required product artifacts additionally need
verified bytes in CAS; a node-local `result_reference` remains compatibility
evidence only.

## Worker and provider rules

- API contracts are the only normal worker transport.
- A runner advertises `runner:<name>` only after a fresh live readiness probe
  or trusted broker attestation. Binary presence or CLI login text is not
  enough.
- A failed or blocked readiness probe removes that capability before another
  lease.
- The requested provider is honored exactly. Fallback requires explicit
  provider policy and is performed by the gateway, not improvised by a worker.
- Provider credentials, cookies, browser sessions and refresh tokens never
  enter task envelopes or move between Mac, Home and workers.
- Code-producing attempts use isolated worktrees, one fenced writer and a
  bounded `write_scope`. Reducers consume commits and verified artifacts, not
  chat memory or mutable worker directories.
- Safe work-trace summaries may be streamed. Private reasoning, credentials and
  arbitrary stdout are not heartbeat payloads.

## API contract status

The OpenAPI document is authoritative for the public surface. Its current
implementation markers are intentional:

- `GET/POST /v1/tasks` are `compatibility`;
- `GET/POST /v1/tasks/{task_id}/events` are `target`;
- `/v1/runtime/actors` and `/v1/runtime/summary` are `compatibility`;
- `/v1/runtime/dags` and `/v1/runtime/pools` are `target`.

The internal compatibility worker lifecycle currently includes node
registration/heartbeat, lease, task heartbeat, complete, fail and cancel
routes in `ops/factory_control.py`. Their request/response shapes are frozen in
`control-plane.schema.json`; they are not a license to invent a second public
API list in documentation.

Compatibility routes may remain for two verified release waves. They must map
to the same Home task authority and cannot become a parallel queue. Target-only
OpenAPI routes remain unavailable until their implementation, persistence and
contract tests pass.

## Fleet truth and the meaning of 21/21

Three independent facts must be reported separately:

1. **Bootstrap connectivity:** Mac/Home can reach the 21 physical servers.
2. **Agent freshness:** Home sees a fresh canonical Agent Host observation.
3. **Execution proof:** a node completed a real capability task through the
   strict lifecycle.

Membership or heartbeat proves neither provider execution nor task completion.
`21/21` is valid only for a fresh, release-bound campaign whose denominator is
the canonical signed mesh manifest and whose every node has:

- a Home-issued attempt and positive fence;
- matching node/agent lease ownership;
- task heartbeats across the required execution window;
- a non-empty result and content hash;
- immutable artifact evidence when the task declares an artifact;
- a passed independent verifier bound to the same attempt;
- retained task, event and evidence identifiers for audit.

Mac is an optional Apple/provider worker and is not silently added to the
server denominator. A missing observation is `unknown` or `unavailable`, never
zero work, online or completed. Fleet readiness is not inferred from a static
card, a declared capability or a successful registration.

## Release gate

Before the compatibility Control Plane can be used to roll out Agent Hosts:

1. freeze the exact Agent Runner, Control Plane schema and OpenAPI commit;
2. run focused task/attempt/fence/completion contract tests;
3. produce and review the digest-bound Home-only plan;
4. run the read-only side-by-side candidate;
5. restart only Factory Control with backup and automatic rollback armed;
6. prove one real task, including a late-completion rejection after worker loss;
7. only then begin signed progressive worker rollout and a new 21-node campaign.

Until every applicable gate passes, report the factory as compatibility or
partial. Do not claim operational readiness from documentation or source code.
