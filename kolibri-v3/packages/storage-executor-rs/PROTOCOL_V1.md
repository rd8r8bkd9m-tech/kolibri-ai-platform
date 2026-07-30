# Storage executor protocol v1

Transport carries one UTF-8 JSON object and is bounded by signed policy
(`maxRequestBytes`, hard ceiling 256 KiB). Unknown JSON fields fail parsing.

## Request envelope

```json
{
  "protocolVersion": "v1",
  "requestId": "request-inventory-0001",
  "command": {
    "kind": "inventory",
    "nodeId": "home"
  }
}
```

Commands:

```json
{"kind":"inventory","nodeId":"home"}
```

```json
{
  "kind":"preview",
  "nodeId":"home",
  "category":"cache",
  "operationKind":"cleanup"
}
```

Project lifecycle preview omits `category`:

```json
{
  "kind":"preview",
  "nodeId":"home",
  "operationKind":"quarantine",
  "projectId":"candidate-01"
}
```

`restore` and `purge` accept only a node-issued/central opaque
`quarantineId`. Execute binds the durable central operation ID to the preview:

```json
{
  "kind":"execute",
  "operationId":"sop_0123456789abcdef0123456789abcdef",
  "previewRef":"spx_0123456789abcdef0123456789abcdef",
  "nodeGeneration":"gen_0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "projectId":null,
  "quarantineId":null
}
```

For quarantine execute, `projectId` must equal preview and `quarantineId` must
match `sqn_<32 lowercase hex>`. For restore/purge, only the matching
`quarantineId` is present.

```json
{
  "kind":"status",
  "operationId":"sop_0123456789abcdef0123456789abcdef"
}
```

## Response envelope

Success:

```json
{
  "protocolVersion":"v1",
  "requestId":"request-inventory-0001",
  "ok":true,
  "result":{"kind":"inventory","data":{}}
}
```

Failure:

```json
{
  "protocolVersion":"v1",
  "requestId":"request-inventory-0001",
  "ok":false,
  "error":{
    "code":"guard_evidence_unavailable",
    "message":"Exhaustive live guard evidence is unavailable.",
    "retryable":false
  }
}
```

Errors never include a path, shell output, policy contents or a raw internal
exception. `operation_incomplete` leaves the durable operation in `applying`;
the caller retries the identical execute request or uses `status`.

## Idempotency

- Preview is keyed by `requestId` and request digest.
- Execute is keyed by `operationId` and the entire execute command digest.
- An identical replay returns the durable result with `replayed: true`.
- Reusing either key for another payload fails closed.

The current protocol implementation is capacity/topology-only:
`guardedScopes` is always empty, every actionable candidate/count/byte field
is zero, and effective execution is disabled in release, debug and custom
builds. Omitted, invalid or successfully parsed enumerated `guardEvidence`
never changes that result. Preview and execute always fail with
`guard_evidence_unavailable`. Parsed files are not yet an exhaustive live
config/daemon-generation attestation and therefore cannot authorize a
protection scope or mutation.
