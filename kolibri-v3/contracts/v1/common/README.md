# Kolibri common contracts v1

Task: `P02-T01`

This directory defines transport-neutral envelopes shared by the Logical Home
Control Plane, Product/Data Authority, Provider Execution Authority, agents,
workers and UI adapters. Physical server names are never authority names.

## Identity semantics

- `tenant_id` is the security and data-isolation boundary. It is required on
  every command and retained on derived events.
- `user_id` is the end user on whose behalf work is performed. It is required
  but may be `null` only for an authenticated system-initiated operation.
- `actor` is the authenticated principal that sent the command: user, service,
  agent or system process. An agent acting for a user does not become that
  user.
- `authority` is a verified policy grant, not a self-declared role. The
  receiving boundary must reconstruct or verify it from authenticated
  transport/policy state before accepting a modifying operation.
- Logical owner values are limited to `logical_home_control_plane`,
  `product_data_authority` and `provider_execution_authority`. Human approval
  is a separate policy/sign-off gate and never becomes a fourth data or command
  owner.
- `authority_role` is logical. `authority_placement_id` records the concrete
  runtime placement for audit and fencing; it does not grant authority.
- `goal_id`, `case_id` and `task_id` are nullable because intake may create
  them. When present, `task_id` requires both `case_id` and `goal_id`, and
  `case_id` requires `goal_id`.

Identifiers are opaque, tenant-scoped where applicable and never reused.
Callers must not infer server, region, time or permission from an identifier.

## Command, event and error semantics

- A command is an intent sent to exactly one logical owner. Acceptance means
  the owner has durably accepted or rejected it, not that a memory queue
  contains it.
- An event is an immutable fact emitted by the canonical owner after a durable
  transition. Consumers may receive it at least once and out of order.
- An error is a stable, non-secret machine-readable failure. `safe_message`
  may be shown to a user; `details` must remain redacted.
- `trace_id` correlates a journey. `correlation_id` groups related messages.
  `causation_id` identifies the immediate command/event that caused a message.
- A command `idempotency.key` identifies one intended canonical effect inside
  its declared `scope` and `scope_id`. For tenant/goal/case/task scope,
  `scope_id` must exactly match the corresponding ID in `identity`. Aggregate
  scope is checked by the named domain payload schema. Retries reuse the key
  and canonical effect. Reusing a key with a different canonical request hash
  is `idempotency_conflict`.
- Events use `deduplication_key` plus aggregate version. Consumers persist an
  inbox key and make duplicate delivery a no-op.

`canonical_request_hash` is `sha256:` plus the lowercase SHA-256 digest of the
UTF-8 RFC 8785 JSON Canonicalization Scheme representation of this object:

```json
{
  "schema_id": "...",
  "schema_version": "...",
  "command_name": "...",
  "payload_schema_id": "...",
  "payload_schema_version": "...",
  "target_owner": "...",
  "tenant_id": "...",
  "user_id": "...",
  "actor": {},
  "subject_refs": {},
  "idempotency_scope": "...",
  "idempotency_scope_id": "...",
  "payload": {}
}
```

Transport-varying values (`message_id`, timestamps, trace/span IDs), the
verified authority decision and the hash field itself are excluded. Thus a
retry may receive a new trace and refreshed authority grant without changing
the intended canonical effect, while a changed actor, subject, owner or
payload conflicts. RFC 8785-invalid Unicode, including a lone UTF-16 surrogate
in a value or object key, is rejected before hashing and produces the
fail-closed `canonicalization_failed` violation.

## Version and unknown-field policy

1. `schema_id` selects the envelope family and `schema_version` selects its
   major/minor contract. v1 accepts only the exact values in these schemas.
2. Envelope objects and common nested objects use
   `additionalProperties: false`. Unknown fields fail closed.
3. `payload` and error `details` are extension points. A producer and consumer
   must validate `payload` against the required
   `payload_schema_id`/`payload_schema_version`; the common envelope alone is
   not sufficient for boundary acceptance.
4. Additive fields require a new compatible schema version and dual
   producer/consumer fixtures. Removing, renaming or changing meaning requires
   a new major directory and expand/migrate/contract rollout.
5. An unknown schema ID/version returns `unsupported_schema` and is neither
   queued nor partially applied.
6. Stored commands/events retain their original bytes, schema ID/version and
   canonical hash. Active workflows remain pinned to compatible versions.

## Boundary validation order

1. size/content-type limit;
2. envelope schema;
3. authenticated actor and tenant binding;
4. verified authority grant, epoch, placement and capability;
5. domain payload schema;
6. deadline and budget;
7. idempotency scope, RFC 8785 canonicalization/hash and conflict check;
8. durable owner-local mutation and outbox event.

The reference common-envelope validator additionally rejects a command whose
deadline is not after issuance, a scope ID that does not equal the identity
subject, an event recorded before it occurred, or a source command that is not
the immediate trace cause. It also rejects a changed canonical effect with a
stale hash and malformed Unicode before hashing. These cross-field checks are
intentionally tested outside Draft-07 JSON Schema.

Valid and deliberately invalid fixtures are in `examples/`. Run:

```bash
backend/venv/bin/python -m pytest -q tests/test_common_contract_schemas.py
```
