# Kolibri Artifact contracts v1

Task: `P02-T04`.

`Artifact` is an immutable version record. Product/Data Authority owns the
bytes and their storage adapter; Logical Home Control Plane owns the canonical
metadata, lifecycle, evidence/review/sign-off graph and release eligibility.
A physical server name is never an owner or authority.

## Identity and lineage

An artifact version is identified by the exact tuple
`(tenant_id, artifact_id, artifact_version, content_hash)`. The record binds:

- the Goal, ProjectCase and optional Task;
- one Product/Data domain aggregate and its exact version;
- verified media type, byte size, content hash and opaque storage reference;
- schema, renderer, generator and execution versions;
- every exact input ID, kind, version, hash and role;
- structured provenance with actor/tool and recorded/effective timestamps.

The content/version record is never edited. A replacement is a new
`artifact_version` with `supersedes`. `artifact-state.schema.json` is a
separately versioned lifecycle projection; stale or revoked state does not
erase the old bytes or manifest.

## Lifecycle and writes

The canonical lifecycle is declared in `artifact-transitions.json`. Stale
transitions identify the exact changed input(s). `revoked` and `superseded`
are terminal. Released versions remain auditable after becoming stale.

`artifact-state-transition.schema.json` is a payload contract. Every write
MUST be wrapped in `contracts/v1/common/command-envelope.schema.json` with
tenant/actor/authority/goal/case/task, trace, exact schema version and
idempotency fields. The reference command validator additionally requires:

- `target_owner = logical_home_control_plane`;
- authority role `logical_home_control_plane`;
- capability `artifact.lifecycle.transition`;
- a current owner-local state/version check before mutation.

## Current runtime compatibility

`kolibri-backend/app/artifact_store.py` already has content-addressed bytes,
SHA-256 verification and immutable numeric `revision` manifests. During
expand/migrate, its `(id, revision, sha256)` maps to
`(artifact_id, artifact_version, content_hash)`. Existing public URL fields
remain Product/Data projections and are not copied into the canonical
authority contract. Arbitrary filesystem paths from legacy factory envelopes
are not canonical storage references.

Unknown fields and any old/new `schema_version` fail closed. A compatible
additive revision requires a new accepted schema version and dual fixtures; a
breaking change requires a new major directory and expand/migrate/contract.
