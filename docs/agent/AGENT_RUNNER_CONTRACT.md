# Kolibri Agent Runner Contract

Status: Home-first implementation contract, 2026-07-12.

This document defines the boundary between the logical Home Control Plane and
every Execution Plane runner. It supersedes the June 2026 runner notes. The
frozen product contract remains
`docs/KOLIBRI_OS_V1_CONTRACT_FREEZE.md`; this document narrows it to task
leasing, execution and completion.

Normative terms:

- **REQUIRED** is the release contract.
- **COMPATIBILITY** describes behavior implemented by the current
  `ops/agent_host.py` and `ops/factory_control.py` while the Rust authority is
  built.
- **LEGACY** may be read only during the two-wave migration window. New tasks,
  releases and tests must not produce it.

The presence of a binary, a heartbeat, an HTTP `200`, a provider reply, a local
file or the word `completed` is never execution proof.

## Authority and transport

- The only logical task authority is `control-plane/home`. A hostname or IP is
  discovery metadata, not durable identity.
- Every mutation is bound to the current positive `authority_epoch`. A runner
  must reject an older epoch and stop the affected process group.
- Workers register, lease, heartbeat, checkpoint, complete and fail through
  Home API contracts. **SSH is not worker transport.** SSH is reserved for
  owner-approved bootstrap, diagnostics and emergency recovery.
- Provider fallback never changes task authority. Mimo, Codex, specialized
  providers and local models are Execution Plane routes beneath Home.
- Mac is an optional Apple/provider worker. A Mac browser or Codex session is
  never copied to Home or to Linux workers.

### Current compatibility gap

The current Python compatibility Control Plane implements monotonic
`fencing_token`, but it does not yet persist or validate `authority_epoch`.
Until the Rust/quorum authority adds that field, the runtime is a Home-only
compatibility authority, not HA/split-brain proof. A release report must expose
this as `partial`; it must not infer epoch safety from the hostname `home`.

## Durable task envelope

A schedulable task carries, at minimum:

- `task_id`, `idempotency_key`, `kind`, `objective` and acceptance assertions;
- project, workstream, plan, actor and trace identifiers where applicable;
- immutable `base_commit` or immutable release digest for code/release work;
- `required_capabilities` and typed resource/slot requests;
- runner/provider policy, budgets and bounded attempt timeout policy;
- `max_attempts`, the total number of attempts including the first;
- `write_scope`, worktree policy and effective permissions;
- required artifact types and verifier gates;
- approval, FormulaLM consent/license and retention policy;
- `ContextPack` reference or embedded `kolibri.context-pack.v1` projection.

`max_attempts` is canonical and is an integer from 1 through 100. During the
compatibility window only, incoming `max_retries` is translated to
`max_attempts = max_retries + 1`. Supplying both spellings with different
budgets is a `409` contract conflict. New producers must never emit
`max_retries`.

Task creation is idempotent. Reusing an idempotency key with an identical
canonical request returns the existing task. Reusing it with a different
request hash returns `409`; it never silently replaces the task.

## Kinds, capabilities and resources

The Swarm plan role kinds are `planner`, `worker`, `reducer`, `verifier`,
`approval` and `release`. They are durable orchestration roles, not necessarily
Agent Host dispatch names.

The current compatibility Agent Host supports these dispatch kinds:

- `owner_remote_task`;
- `orchestrator_chat_response` and `telegram_chat_response`;
- `image_generation` and `telegram_image_generation`;
- `read_only_probe` and `lease_heartbeat_probe`;
- `review_pr`;
- `impl_factory_smoke` and `impl_retry_error_clearance`;
- `direct_mimo`, `mimo_direct` and `mimo_task` as LEGACY direct-runner aliases;
- `release_bundle_apply` and `release_bundle_rollback` through the narrow
  privileged release helper.

Unknown kinds or missing required capabilities return a structured `blocked`
result without arbitrary execution or product changes.

Capabilities are runtime attestations, not catalog entries. A worker advertises
only capabilities whose dependency, policy and live readiness gates pass.
Examples include resource capabilities (`code`, `test`, `browser`, `build`,
`document`, `model`, `review`, `apple`), runner capabilities (`runner:mimo`,
`runner:codex`) and the signed release capability `release_apply_v1`.

Physical slots are separate from logical actors. The required Agent Host
supports multiple bounded slots and publishes capacity plus current occupancy.
`max_inflight` must constrain simultaneous attempts; CPU, memory, disk,
provider quota and the 20% safety reserve can lower that value dynamically.

### Current compatibility gap

The Python Agent Host parses `max_inflight` but its loop has one
`_active_task_id` and leases/runs one task synchronously. It is therefore a
single-slot compatibility worker. `max_inflight > 1` must not be reported as
working capacity until concurrent attempt scheduling and isolation tests pass.

The compatibility envelope still carries one `required_capability` string.
The required contract uses the `required_capabilities` array; migration may
project a one-item array to the legacy singular field, but new orchestration
code must not lose multiple capability requirements during that projection.

## Registration and heartbeats

Registration and node heartbeat records include:

- opaque `node_id`, `agent_id`, runtime digest and process identity;
- signed membership provenance and `authority_epoch`;
- capabilities and physical slot capacity;
- runner contracts plus redacted readiness status;
- release-installer status and node telemetry;
- `active_attempts`, an array of every active attempt on the process.

Each `active_attempts` entry contains at least:

```json
{
  "task_id": "KOL-TASK-...",
  "attempt_id": "KOL-TASK-...-attempt-2",
  "fencing_token": 7,
  "authority_epoch": 4,
  "slot_class": "code",
  "started_at": "2026-07-12T00:00:00Z",
  "last_heartbeat_at": "2026-07-12T00:00:05Z"
}
```

Task heartbeat repeats `task_id`, `attempt_id`, `fencing_token`,
`authority_epoch`, `node_id` and `agent_id`. It may add bounded, sanitized
`progress`; it never publishes private reasoning, credentials or arbitrary
stdout.

The node heartbeat interval is at most 10 seconds. A task subprocess refreshes
its task lease at most every 2 seconds in the current compatibility runtime.
Loss of the authoritative heartbeat response, cancellation, stale epoch or a
fence mismatch terminates the local process group. Client disconnect alone does
not cancel durable work.

### Current compatibility mapping

The Python Agent Host currently publishes scalar `active_task`, not
`active_attempts`, because it is single-slot. That field is LEGACY projection
only. The multi-slot release gate requires `active_attempts` and forbids deriving
it from one scalar after concurrent execution is enabled.

Registration, heartbeat and readiness-card evidence do not prove provider
execution. `available` becomes execution proof only after a content-bound live
invocation, and a task cancelled before lease is not an execution result.

## Lease, attempt and fencing

Home assigns all authoritative attempt fields:

```json
{
  "attempt_id": "KOL-TASK-...-attempt-2",
  "lease_owner": "node-id:agent-id",
  "lease_until": "2026-07-12T00:01:00Z",
  "fencing_token": 7,
  "authority_epoch": 4
}
```

Rules:

1. `fencing_token` is a positive integer, monotonically increasing per task.
2. `authority_epoch` is a positive integer, monotonically increasing per
   Control Plane authority term.
3. A heartbeat, completion or failure must match the authoritative attempt,
   owner, node, agent, fence and epoch.
4. A mismatch or late completion returns `409`; the result may be retained as
   quarantined evidence but cannot mutate task state.
5. Lease expiry consumes the current attempt. The task returns to the queue
   only while `attempt < max_attempts`; otherwise it becomes `dead_letter`.
6. A retry receives a new `attempt_id` and a strictly larger `fencing_token`.
7. The worker must not invent or increment authoritative fields locally.

The Python compatibility runtime recognizes pre-fencing Redis records only long
enough to migrate them on the next lease. New records always carry
`kolibri.lease-fencing.v1`; deleting one fencing field never downgrades a task.

## Runner readiness and authentication truth

Runner readiness has four states: `available`, `degraded`, `blocked` and
`unavailable`. A binary path or CLI `login status` alone is not `available`.
The state must be backed by a bounded live invocation or a fresh trusted-broker
attestation with a timestamp, model, sandbox, output hash and normalized error.

Only `available` may add `runner:<name>` to node capabilities. Failures such as
`runner_auth_blocked`, `runner_auth_failed`, `runner_access_denied`,
`runner_policy_blocked`, `provider_risk_control`, `runner_unavailable` or
`provider_runner_outdated` withdraw that capability before the next lease.

Credentials are node-managed or broker-scoped. Tasks never contain passwords,
cookies, refresh tokens, API keys or browser sessions. A runner may report an
opaque authorization reference, but not secret material. Readiness and result
logs are redacted.

### Safe provider routes

- Public identity is always `kolibri`; the requested internal runner is audit
  metadata.
- A factory response task is read-only and worktree-scoped.
- Mimo response generation uses the pinned response-only profile, no tools,
  JSON output, prompt-by-file and a read-only sandbox.
- Codex factory generation uses a pinned model contract, prompt on stdin,
  read-only sandbox and provider-managed web search.
- Controlled web search is bounded and hash-evidenced. Arbitrary `curl`/`wget`
  network access is not substituted for the search capability.
- Provider proxy variables are injected only into provider child processes.
  Home API, mesh, build commands and the Agent Host itself remain on canonical
  routes.
- A requested runner is honored exactly. Fallback is allowed only by an
  explicit, audited provider policy and is performed by the gateway, not by a
  worker improvising after failure.
- A failed provider attempt is an internal event. It is terminal for the user
  only after all policy-approved routes are exhausted.

The write-capable Mimo/Codex direct invocation descriptions are LEGACY. They
must not be selected for public response tasks or advertised as the safe
factory provider contract.

## Context, worktrees and permissions

Code-producing attempts receive one isolated worktree under the Agent Host task
root. Durable identity is the task/attempt plus immutable `base_commit`, never
the local path. One attempt has one fenced writer and a strict `write_scope`.
Reducers consume commits and verified artifacts, not an agent's chat memory.

`ContextPack` supplies the goal, current plan step, decisions, checkpoints,
acceptance assertions, base commit and permitted paths. Mac, Home CLI, Codex and
Mimo resume through that durable context; local conversation state is not
authority.

Read-only/no-push enforcement remains fail-closed:

- `read_only`, `no_push` or `git_push_forbidden` removes push/full-autonomy
  permissions, and any write-worktree task carrying those constraints is
  blocked before its runner executes;
- `product_code_modification_forbidden` blocks non-document product changes;
- `documentation_artifacts_only` permits only `docs/**`, the task artifact
  directory and explicit `write_scope`;
- every changed path must match `write_scope` when it is present;
- push-capable implementation work runs the complete contract preflight before
  `git push`; a failed preflight skips the push.

For declared backend verification, a temporary Python environment is created
under the artifact directory, never the worktree. The envelope must explicitly
declare the interpreter, requirements/packages and cleanup policy. Setup failure
is `backend_test_environment_failed`, not a passed verification.

## Runner result

The local contract finalizer persists at least:

- task, attempt, fence and epoch binding;
- `status`, `requested_runner`, `runner` and `runner_binding_verified`;
- changed files, write scope and violations;
- read-only/product-code/push policy results;
- required artifacts present/missing;
- tests and checks;
- artifact manifest, result reference and next recommended task;
- normalized blocker/failure reason without secrets.

Runner contract statuses are only `completed`, `blocked` and `failed`.
Domain review states such as `APPROVED` or `CHANGES_REQUESTED` belong in
`runner_status`; they do not replace the contract status.

Unsupported work, missing artifacts, scope violations, forbidden push,
permission mismatch, requested-runner mismatch or unavailable authorization
cannot produce a completed runner result.

Owner-facing canonical run directories, when requested, contain exactly:
`PLAN.md`, `ACTIONS.md`, `TESTS.md`, `RESULT.md` and `NEXT.md`. An explicitly
declared complete alias may be copied into the canonical directory; fuzzy
directory discovery is forbidden.

## Artifact materialization and CAS

`artifact_dir` and a node-local `result.json` are attempt scratch/evidence, not
the durable artifact authority. Before a product artifact is `ready`, the
artifact service materializes bytes into immutable content-addressed storage
and records:

```json
{
  "schema_version": "kolibri.artifact.v1",
  "artifact_id": "art_...",
  "uri": "artifact://sha256/<digest>",
  "media_type": "application/pdf",
  "size_bytes": 12345,
  "sha256": "sha256:<64 lowercase hex>",
  "task_id": "KOL-TASK-...",
  "attempt_id": "KOL-TASK-...-attempt-2",
  "fencing_token": 7,
  "authority_epoch": 4
}
```

The task result references the immutable CAS record and its hash. A path,
caption, claimed image URL or file name without verified bytes is not an
artifact. A replacement creates a new artifact and lineage edge.

### Current compatibility gap

The current Agent Host writes `artifact-manifest.json` with local file hashes,
and the Python Control Plane accepts a non-empty node-local `result_reference`.
That is useful compatibility evidence, but it is not durable CAS proof. Release
readiness for documents, images, builds and other product artifacts requires
materialization into CAS plus a bound artifact verifier.

## Exact completion and independent verifier

The worker calls `/v1/tasks/{task_id}/complete` only after local contract
preflight. Its payload binds:

- `attempt_id`, `fencing_token`, `authority_epoch`, `node_id`, `agent_id`;
- the non-empty canonical result object;
- immutable `result_reference`;
- optional claimed `result_sha256` and `binding_sha256` for comparison.

Home independently canonicalizes the result and computes:

```text
result_sha256 = SHA-256(canonical JSON result)
binding_sha256 = SHA-256(
  schema + task_id + attempt_id + lease_owner + fencing_token
  + authority_epoch + result_reference + result_sha256
)
```

The persisted records are:

- `kolibri.task-completion-evidence.v1`;
- `kolibri.task-completion-binding.v1`;
- `kolibri.control-plane-completion-verifier.v1` with
  `verifier: control-plane/home`, `independent: true`, all checks true and
  `verdict: passed`.

Home verifies task state, attempt, owner, node, agent, fence, epoch, successful
runner status, result reference, result hash and binding hash. Where artifacts
are required, it also verifies CAS bytes/hash/media type and the declared
artifact verifier. Producer and verifier identities must be independent under
the task verifier policy.

Only then may task state become `completed`. Stored completion truth is
recomputed from the result and binding; a persisted `verdict: passed` is not
trusted by itself. `/fail` uses the same attempt/fence/epoch binding and cannot
retry beyond `max_attempts`.

### Current compatibility gap

`ops/factory_control.py` already creates and recomputes the three completion
records and validates attempt/owner/node/agent/fence/result hashes. Its binding
does not yet include `authority_epoch` or a CAS object. These are explicit
cutover blockers, not optional metadata.

## Release compatibility table

| Surface | Status | Rule |
| --- | --- | --- |
| Home API task lifecycle | COMPATIBILITY | Sole live task authority; fenced attempts and independent result verifier required. |
| Redis task state | LEGACY compatibility | Removed after two verified release waves; never a second authority. |
| Scalar `active_task` | LEGACY projection | Single-slot only; replaced by `active_attempts`. |
| `max_retries` | LEGACY input alias | Read/translate only; new tasks emit `max_attempts`. |
| Pre-fencing Redis task | LEGACY migration record | Upgraded on next lease; no new record may omit fencing. |
| Direct Mimo/Codex write paths | LEGACY | Never public response routing; remove after bounded task adapters exist. |
| Local artifact path | COMPATIBILITY evidence | Not product-ready until bytes are in CAS and verified. |
| SSH task launch | Forbidden | Operator diagnostics/bootstrap only. |
| Rust multi-slot Agent Host | REQUIRED target | Must pass isolation, resource and active-attempt tests before authority. |
| Rust/quorum `authority_epoch` | REQUIRED target | Must pass stale-leader and stale-attempt tests before HA claim. |

## Machine-checkable release assertions

A runner/Control Plane release must fail when any assertion below is false:

1. Home is the only configured task authority and no `main`/`primary` fallback
   exists.
2. New tasks contain `max_attempts`, fencing schema and initial token zero.
3. Every lease increments the positive fence and carries the current authority
   epoch.
4. Late attempt, stale fence, stale epoch, wrong node or wrong agent mutations
   return `409`.
5. Node heartbeats publish exact `active_attempts`; occupancy never exceeds
   admitted slots.
6. A failed runner readiness probe withdraws `runner:<name>` before another
   task can lease it.
7. Code attempts cannot share a worktree or write scope.
8. Completion has a non-empty result, CAS-bound required artifacts and a passed
   independent verifier whose hashes recompute exactly.
9. Worker work is submitted through API contracts, never SSH.
10. Compatibility gaps above remain visible as `partial` until their dedicated
    tests pass; documentation or heartbeat cannot promote them to ready.
