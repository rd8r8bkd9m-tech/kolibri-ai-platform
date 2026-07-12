# Kolibri OS V1 contract freeze

Status: implementation contract, 2026-07-10.

This document freezes the boundary between the current FastAPI/React runtime
and the Rust Control Plane. It does not claim that a production rollout or a
21-node capability verification has already happened.

## Non-negotiable invariants

1. `kolibri` is the public model and product identity. Provider selection is an
   internal, auditable detail.
2. The Control Plane schedules, leases, checkpoints and verifies work. It does
   not perform provider inference or build work itself.
3. A logical actor is durable state plus a mailbox. It is not an operating
   system process. At least 1000 actors may be active while physical slots stay
   bounded by node telemetry and provider quotas.
4. Every mutating request carries an idempotency key. State mutation and event
   publication use an outbox/inbox boundary so retries cannot double-execute a
   transition.
5. A response can be `completed` only after its declared verifier gates pass.
   A heartbeat, accepted HTTP request or provider response alone is not proof.
6. FormulaLM receives sanitized, provenance-bearing learning records only.
   Production model weights never mutate synchronously in a customer request.
7. Owner approval remains mandatory for production, credentials, money,
   destructive actions and security-sensitive mutations.
8. Existing `/v1/fabric/*`, `/v1/agents/*` and Superfactory routes remain
   compatibility aliases until two release waves have consumed the V1 surface.
9. The known-good Mac-to-fleet bootstrap and mesh are external infrastructure
   invariants. Product rollout must not rewrite that network configuration.
10. `home` is the only canonical Control Plane identity. `main`, `primary`,
    `primary-candidate` and historical Control Plane endpoints are never
    scheduler or release fallbacks; healthy instances may participate only as
    workers. Runtime endpoints are resolved from the signed fleet manifest or
    service environment. Provider fallback is an Execution Plane concern and
    must never change Control Plane identity.
11. Durable projects, responses, task transitions, artifacts, learning data,
    runtime controls and owner operations require an authenticated API
    principal. The compatibility API fails closed when no bearer credential is
    configured. The public Shell uses a short-lived opaque HttpOnly session
    bound to exact Origin and may create/read only its own ephemeral project
    and responses. Only the session-token hash is stored. It never receives
    durable project, artifact, runtime, learning or owner authority merely
    because it is same-origin.
12. A task may enter `leased`, `running` or `completed` only for the matching
    `attempt_id` and `lease_owner`. `completed` additionally requires
    content-bound evidence and a passed verifier bound to that attempt.

The machine-readable definitions are in
`contracts/kolibri-os-v1/domain.schema.json`; the frozen public HTTP surface is
in `contracts/kolibri-os-v1/openapi.json`. The fail-closed local-model and
FormulaLM admission reports are defined separately in
`contracts/kolibri-os-v1/model-and-learning-policy.schema.json`; that policy
contract never authorizes copying third-party weights or private reasoning.

## Durable identifiers and versions

- All records carry `id`, `schema_version`, `created_at` and `updated_at`.
- IDs are opaque and stable. A hostname, IP address, provider name or worktree
  path is metadata and must never be used as durable identity.
- The initial schema family is `kolibri.*.v1`. Additive fields are compatible;
  removed fields, changed meaning or narrowed enums require a new version.
- `trace_id` follows a complete client request. `task_id`, `actor_id`,
  `attempt_id` and `artifact_id` identify nested durable records.

## State machines

### Response

```text
queued -> planning -> running -> verifying -> completed
   |          |          |           |
   +----------+----------+-----------+-> failed | cancelled | incomplete
```

`completed`, `failed`, `cancelled` and `incomplete` are terminal. A provider
failure is an event and a route attempt, not automatically a terminal response.

### Task / plan node

```text
pending -> ready -> leased -> running -> review -> completed
                        |        |          |
                        +--------+----------+-> retry -> ready
                        +-------------------> blocked | dead | cancelled
```

Only the current lease owner may emit running/review/completed transitions.
Lease attempts are fenced by `attempt_id`; late results from an expired attempt
are stored as evidence but cannot change authoritative task state.

### Actor

```text
idle -> runnable -> leased -> running -> checkpointing -> idle
                    |          |
                    +----------+-> waiting | failed | stopped
```

Actor state and mailbox survive worker loss. Resource slots are leased
separately, allowing thousands of logical actors to share a bounded number of
CPU, model, browser and build slots.

### Artifact and preview

```text
declared -> materializing -> ready -> verified
                       |          |
                       +----------+-> failed | expired | quarantined
```

Artifacts are content-addressed and immutable. A replacement creates a new
artifact and lineage edge; it does not overwrite the previous object.

## Event envelope

Every durable transition emits a CloudEvents-like envelope:

```json
{
  "schema_version": "kolibri.event.v1",
  "id": "evt_...",
  "type": "provider.attempt.failed",
  "source": "provider-gateway",
  "subject": "response/resp_...",
  "trace_id": "trace_...",
  "sequence": 17,
  "occurred_at": "2026-07-10T00:00:00Z",
  "data": {},
  "provenance": {"actor": "gateway", "policy_version": "v1"}
}
```

Sequence numbers are monotonic per subject. Consumers deduplicate by event ID
and persist inbox position before applying side effects.

## SwarmPlan contract

A `SwarmPlan` is a DAG of typed plan nodes. Each node declares:

- objective, dependencies and acceptance criteria;
- required capabilities and resource class;
- retry, timeout, approval and provider policy;
- isolated worktree/write scope for code-producing tasks;
- reducer group and verifier gates;
- checkpoint and artifact expectations.

The scheduler may reorder ready nodes or use work stealing, but it cannot
weaken acceptance criteria, approval policy or resource limits. Reducers consume
only verified artifacts. A verifier branch may reject a reducer result and
return the affected nodes to `retry` without replaying successful independent
branches.

## Provider routing

Provider attempts are ordered policy records. The default route is:

1. best allowed external general provider;
2. external fallback;
3. specialized tool/provider;
4. internal Kolibri model in shadow mode.

Each failed attempt emits `provider.attempt.failed` with a normalized reason;
secrets and raw credentials are forbidden. The user sees a blocker only after
all allowed routes are exhausted or an approval is required. Internal model
promotion is evidence-gated at `1% -> 10% -> 50% -> 100%`, with explicit
rollback metadata and an external fallback retained.

### Controlled web evidence

`tool:web_search` is a response-scoped read-only capability, not generic
outbound network access. Kolibri accepts a bounded query and executes it only
through fixed HTTPS provider endpoints. Destination DNS, every redirect and
every citation host are checked against private, loopback, link-local and
metadata ranges; timeout, redirect count, response bytes, result count and
provider context are capped. Provider failures are classified and fall through
the allowlisted route. The answering model receives bounded search evidence
marked as untrusted and never receives a shell or arbitrary URL-fetch tool.

The execution record binds response/task, authenticated principal, optional
project/workstream and public-session identity by hashes. Public results expose
citations and content hashes, while FormulaLM receives only the sanitized tool
tap (query/result/citation hashes and source hosts), candidate-only with no
request-path training or automatic promotion.

### Owner project evidence

`tool:project_knowledge` is a response-scoped, read-only owner capability. It
searches only allowlisted repository documentation/source roots beneath the
running release, never follows symlinks and excludes secrets, environment
files, dependencies and runtime/evidence artifacts. Results are bounded and
bind a sanitized excerpt to a repository-relative path, exact line span, file
SHA-256 and span SHA-256. It is not exposed to public sessions and is never a
fallback for internet search. Provider answers must cite the supplied project
markers; the deterministic verifier fails closed without bound citations.

## FormulaLM learning boundary

The synchronous tap records provenance, policy, normalized decisions and
credit assignment. A separate asynchronous job performs sanitization,
license/consent filtering, dataset construction, training or distillation,
independent evaluation and canary promotion.

A `LearningCandidate` must include:

- source trace and artifact hashes;
- consent/license classification;
- sanitization report;
- quality and verifier verdicts;
- intended capability and data retention class.

Candidates containing secrets, private data without consent or license-negative
content are rejected before entering the learning queue.

## Compatibility mapping

| V1 route | Compatibility source | Migration rule |
| --- | --- | --- |
| `POST /v1/shell/bootstrap` | new scoped browser gateway | Atomically creates or resumes an expiring HttpOnly SameSite session after exact-Origin and rate checks; cold startup never relies on an expected 401/403 GET. |
| `POST /v1/public/session` | compatibility alias | Retained for two release waves and delegates to the shell bootstrap contract; no owner credential reaches the browser. |
| `POST /v1/responses` | chat/pipeline and `/v1/agents/tasks` | Canonical OpenAI-compatible JSON/Responses-SSE path. Bearer creates durable work; a public session is idempotent and confined to its ephemeral project. |
| `GET /v1/responses/{id}` | task status helpers | Terminal state requires verifier evidence. |
| `POST /v1/responses/{id}/cancel` | task cancellation | Idempotent; revokes active leases. |
| `GET /v1/models` | current model catalog | Public catalog exposes `kolibri`; provenance remains operator-visible. |
| `/v1/projects/*` | new compatibility store | Later moved to PostgreSQL without changing payload shape. |
| `POST /v1/resume` | new compatibility store | Selects existing workstream unless `create_new=true`. |
| `/v1/runtime/*` | node/task sidecar | Aggregates durable actors and real physical capacity; no mock health. |
| `/v1/canvases`, `/v1/artifacts` | result/artifact helpers | Uses typed renderer and immutable artifact contracts. |
| `/v1/automations` | new compatibility store | Owner-gated by default for external side effects. |
| `/v1/fabric/*`, `/v1/agents/*` | current sidecar | Kept as aliases for two release waves. |

## Persistence boundary

- PostgreSQL is authoritative for projects, workstreams, plans, tasks,
  checkpoints, tenancy and metadata.
- NATS JetStream is authoritative for event delivery and actor mailboxes.
- S3-compatible content-addressed storage is authoritative for artifact bytes.
- Redis is a migration compatibility queue only and is removed after two
  verified release waves.
- The Python compatibility implementation may use SQLite locally, but it must
  preserve the same IDs, versions, idempotency and state semantics so the Rust
  service can take ownership without a UI rewrite.

## Release gates

Contract freeze is necessary, not sufficient, for production. Release requires
contract tests, 1000-actor bounded-slot tests, provider fallback tests,
sanitization tests, browser/build evidence, progressive canary evidence and an
owner-approved protected rollout. Fleet availability is reported separately as
bootstrap connectivity, Agent Host freshness and real capability execution; no
single aggregate number may blur those three facts.
