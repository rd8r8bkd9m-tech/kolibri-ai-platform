# ADR 0001: Durable provider-session acceleration cache

- Status: accepted
- Date: 2026-08-01
- Owners: Kolibri V3 backend

## Context

The V3 backend already starts one long-running `codex app-server --stdio`
process during application lifespan. Keeping only the mapping from a Kolibri
product thread to a Codex thread in Python memory nevertheless discards the
provider context on every backend reload. The next turn then sends the full
canonical chat snapshot to a newly created provider thread and pays cold
context setup again.

Provider context must never become a second chat authority or cross a tenant,
user, project, workspace, model, effort, service-tier, or access-policy
boundary. A provider response may also complete immediately before a backend
failure and therefore be ahead of the committed product history.

The installed Codex CLI `0.146.0` protocol was verified from its generated V2
JSON Schema. `thread/start` accepts `ephemeral: false`, and `thread/resume`
accepts `threadId` plus the same model, cwd, sandbox, approval, reviewer,
instructions, runtime-workspace-root, and service-tier overrides. Its response
returns the effective thread id, model, cwd, sandbox policy, approval policy,
reviewer, service tier, runtime roots, and the thread's `ephemeral` flag.

## Decision

Add an append-only SQLite mapping from the complete Kolibri execution scope to
a materialized provider thread. The scope key includes tenant, requesting user,
project, product thread, credential tenant, runtime profile/id/mode, execution
profile, workspace fingerprint, model, reasoning effort, service tier, sandbox,
approval policy, reviewer, instructions hash, and output-schema hash.

The mapping also records a hash of the canonical product-history head observed
by the provider. The cache is eligible only when that hash matches the history
loaded from the V3 database for the next run. After process restart the first
eligible turn calls `thread/resume`, overrides the exact frozen execution
configuration, and validates the echoed effective configuration before sending
the follow-up prompt. A missing, mismatched, rejected, or invalid resume is
compare-and-deleted and falls back to `thread/start` plus the full canonical DB
snapshot. Cache I/O failure also falls back and must not fail an otherwise safe
model turn.

The existing eager process and per-scope locks remain. Phase 1 resumes sessions
on demand after restart; it does not add a second supervisor or keep every
historical thread loaded. A separate sidecar is not required to preserve
provider context because non-ephemeral Codex threads are materialized by the
verified app-server protocol.

## Consequences

The first turn after a backend reload performs a bounded local resume rather
than rebuilding provider context. Normal in-process turns keep the existing
lock and memory fast path. Model, effort and service tier are always the frozen
values supplied by the accepted run; the cache never selects or downgrades
them.

Codex thread files and the SQLite row are disposable acceleration state. They
may outlive a failed turn until later cleanup, and a cache miss may still incur
a cold provider turn. Product correctness is independent of either artifact.

## Verification

- Migration tests prove the strict table, foreign keys and schema version.
- Store tests prove full-scope isolation and compare-and-delete behavior.
- Protocol tests prove `ephemeral: false`, restart-time `thread/resume`, exact
  configuration overrides, validated stale fallback, and canonical-history
  mismatch fallback.
- Stage timing logs report process readiness, lock wait, account readiness,
  session resolution, turn acceptance, TTFT and total duration without prompts
  or raw product/provider identifiers.
- A safe local benchmark may compare the first post-restart resumed turn with a
  cold new-thread turn while keeping model, effort and tier unchanged.

## Rollback

Stop reading and writing `agent_runtime_session_cache` and return
`thread/start` to ephemeral mode. Do not delete chat messages or rewrite
migration 045. Existing cache rows and provider thread files can remain unused;
removing them later is an explicit garbage-collection operation and cannot
affect canonical product data.
