# ADR 0005: Durable universal estimate orchestration and provenance

- Status: accepted
- Date: 2026-08-02
- Owners: Kolibri V3 backend estimates

## Context

The generic estimate path currently fits inside one chat request: a model
creates a section plan, creates flat rows for each section, and the backend
persists an `EstimateVersion`. That path can prove transport and arithmetic,
but it cannot prove that a large estimate covers the construction process. A
provider timeout, backend restart or one invalid section also loses work which
was already completed.

The product needs a universal pipeline between `ProjectCase` and
`EstimateVersion`. It must persist a project-specific technology-card revision,
research and price evidence, deterministic row lineage and independent review.
The full run may take longer than an HTTP request or provider turn. Removing a
row-count cap is not a solution: a fixture containing 1,200 numbered copies of
one template is still an invalid estimate.

Existing data has three distinct roles which must not be merged:

- `project_cases` owns the versioned interpretation of user inputs;
- `technology_card_definitions` / `technology_card_versions` own reusable,
  reviewed catalog templates, while project `technology_cards` own an accepted
  generated revision after publication;
- `estimate_versions` owns saved calculated estimate snapshots. A model draft,
  task checkpoint or UI page is not an estimate version.

## Decision

Migration 051 introduces a tenant- and project-scoped durable orchestration
boundary owned by the V3 backend:

- `estimate_generation_runs` and `estimate_generation_commands` own accepted
  commands, frozen inputs and lifecycle;
- `estimate_generation_sections` and `estimate_generation_tasks` own durable
  decomposition, roles, attempts and lease state;
- `estimate_generation_checkpoints` owns immutable stage outputs;
- `estimate_generation_technology_revisions` owns an immutable run-local
  technology-card proposal until it is accepted and published;
- `estimate_generation_evidence` owns deduplicated technical and price evidence;
- `estimate_generation_lineage` binds published rows to the exact run, card,
  operation, resource, evidence and line snapshot/hash.

Application or provider caches are never a second authority.

### Run lifecycle

One accepted command creates or reuses an estimate generation run by
idempotency key and request hash. Reusing a key with a different request fails
closed. The run freezes the project-case revision/hash, orchestration version,
calculation rules version, actor, project and target document.

Project attachments are loaded only through tenant/project/thread/run-scoped
metadata and immutable CAS hashes. Supported structured/text formats are
parsed into bounded chunks with explicit parser and truncation status. Their
contents are untrusted user data and cannot override system or skill
instructions; scanned PDFs without a text layer remain an explicit OCR gap.

The persisted stage graph is:

```text
project_case -> decomposition -> technology
  -> research -> pricing -> expansion
  -> reconciliation -> persisting -> complete
```

Tasks are attributed to `technologist`, `quantity_engineer`, `resource_normer`,
`technical_researcher`, `procurement`, `logistics`, `reviewer` or
`orchestrator`. Independent section tasks may execute concurrently. Progress
is derived from persisted task states and weights, never from model prose or
an in-memory counter.

A run can be `queued`, `running`, `needs_input`, `review`, `ready`, `failed` or
`cancelled`. A section can be `pending`, `active`, `needs_input`, `review`,
`passed`, `failed` or `cancelled`. A task can be `queued`, `leased`,
`succeeded`, `failed`, `cancelled` or `superseded`. `failed` and `cancelled`
retain all accepted checkpoints and do not delete source evidence.

There is no product-level two-minute deadline and no row-count completion
condition. Each provider call still has a finite timeout, cancellation and
retry policy. Exhausting a task attempt records a durable error and leaves the
run resumable. Retrying a section invalidates only that section and its
downstream derived checkpoints.

### Leasing, fencing and idempotency

A worker claims a runnable task with a time-bounded lease and monotonically
increasing fencing token. Heartbeats may extend the current lease. Only the
holder of the current token may append an accepted checkpoint or change the
task terminal state. A late response from an expired worker is recorded as
rejected diagnostic evidence and cannot overwrite newer work.

Task identity is stable for `(run, stage, section, input_hash)`. Checkpoints
are immutable and content-addressed; repeating the same accepted output is a
no-op. A changed upstream hash creates a new task input lineage instead of
mutating historical output. Cancellation stops new claims but does not erase
the journal.

### Technology card, evidence and row lineage

The technology checkpoint first creates an
`estimate_generation_technology_revisions` snapshot with `schemaVersion`,
`rulesVersion`, sections, operations, assumptions and exclusions. Every
operation has a stable `operationId`, `sectionKey`, title, method, unit,
quantity formula, predecessors, resources and quality controls. Every resource
has a stable resource ID, kind, title, unit, quantity formula, specification,
quantity basis and optional price-evidence ID.

After review, publication materializes that accepted revision byte-equivalent
into an existing project `technology_cards` record and stores its ID in
`published_technology_card_id`. The run-local revision remains immutable
journal evidence; project `technology_cards` becomes the canonical published
domain artifact. Reusable `technology_card_definitions` /
`technology_card_versions` may seed the proposal but never replace either
artifact.

Evidence is stored once and referenced by tasks and estimate rows. Evidence is
`technical` or `price`; its source is `user_input`, `approved_catalog`,
`official_reference`, `supplier_offer`, `market_aggregate` or `ai_candidate`.
It records source URI/reference/title, observation time, region, original
unit/specification, tax and delivery treatment, validity/freshness, snapshot
hash and confidence. Search snippets and model memory are not source evidence.
An `ai_candidate` is hard-limited to `preliminary`.

Deterministic expansion produces separate `work`, `material`, `equipment`,
`service`, `overhead`, `tax` and `contingency` rows. Each accepted row lineage
binds at least:

- estimate document/version and row ID;
- generation run and producing task/checkpoint;
- project technology-card ID/version/hash and `operationId`;
- quantity formula/basis and source-input provenance;
- zero or more evidence records used for its price/status.

Project inputs carry decimal values, canonical units and provenance. Quantity
formulas are an allowlisted recursive AST (`variable`, `constant`, `multiply`,
`add`, `divide`, `ceil`), not provider code or free-form expressions. Unknown
units, unsafe formula shapes and dimensional mismatches fail validation for
the affected section and may be retried; the backend never guesses a unit.

An `EstimateVersion` is published only in one backend transaction after the
calculation and independent-review gates pass. The transaction freezes the
technology-card reference, lineage and evidence set used by the snapshot.
`source_backed` and `verified` rows require valid evidence; `missing` and
`preliminary` rows must remain honestly labelled. The backend calculation is
authoritative; provider arithmetic and JavaScript totals are not.

### Read and presentation contracts

Chat presents only a compact document reference: project, document, version,
status, summary/row count and server totals. Its `rowPage` explicitly has
`offset=0`, `limit=0`, the authoritative total and `hasMore`; it never embeds
rows in tool arguments or chat history.

Web and mobile read estimate rows in bounded pages. Edits use optimistic
versioning and delta payloads (`upsertRows` / `deleteRowIds`) rather than
resending the complete snapshot. Exports and official packs always render a
selected saved `EstimateVersion`, not a checkpoint or client-side row set.

## Consequences

Runs survive backend and worker restarts, verified sections are reusable, and
one failed provider call does not discard the rest of the estimate. Row
provenance becomes queryable and an official document can be reproduced from
one immutable version.

The cost is additional tables, orchestration state transitions, evidence
retention and operational cleanup. Large runs may stay `needs_input` or
`failed` until a user or worker resumes them. Migration 051 must therefore be
append-only, tenant-scoped and safe for existing estimates, which remain
readable without backfilled fictional lineage.

The first rollout may keep Python Decimal as calculation authority. The Rust
kernel remains shadow/conformance until golden-corpus parity is demonstrated;
this ADR does not authorize a big-bang authority switch.

## Verification

- Migration 051 applies to clean and upgraded databases, passes
  `PRAGMA foreign_key_check`, and proves tenant/project isolation.
- Contract tests prove command idempotency, request-hash conflict, task
  uniqueness, fencing rejection, checkpoint immutability, restart recovery,
  targeted section retry and cancellation.
- Integration tests prove persisted `ProjectCase` and technology card,
  evidence and row lineage, deterministic totals, transactional publication,
  page reads, delta edit/version conflict, reload, export and official pack.
- Semantic quality tests reject numbered placeholders, template-dominant rows,
  unexplained exact duplicates, missing operation/card linkage and false
  `source_backed`/`verified` status.
- Fixture tests are labelled transport/persistence only. They cannot satisfy
  live-model acceptance.
- Live GPT/Codex or MiMo acceptance for the reference nine-storey building
  requires at least 1,000 meaningful atomic rows, at least 15 covered
  technology sections, all four resource kinds, complete quantity basis,
  honest evidence status, server totals and lossless saved-version exports.
- Compact presentation stays bounded independently of estimate row count; web
  and mobile prove page/edit/reload behavior without a full-snapshot PATCH.

## Rollback

Stop claiming new tasks and let active leases expire. Disable new universal
runs, keep reading already published `EstimateVersion` snapshots, and retain
all migration-051 rows as an audit journal. Do not rewrite or drop migration
051 and do not delete project cases, technology cards, evidence, lineage or
estimate versions. A later forward migration may archive orphaned unfinished
runs after a documented retention decision. Existing special calculators may
remain explicitly addressable, but they must not silently become the generic
estimate fallback.
