# FormulaLM learning boundary

Status: Python compatibility implementation, 2026-07-10.

This document defines the implemented boundary between customer execution and
FormulaLM learning. It does not claim that training infrastructure, an eval
council, model weights, or a production canary have been deployed.

## Invariant

`POST /v1/responses` may perform one bounded FormulaLM operation: insert an
intake audit record and, if policy and scanning pass, a sanitized trace into a
durable queue. It does not construct a dataset, train/distill a model, change a
model weight, start a canary, or promote a candidate.

Candidate construction runs through the separate queue-worker route. Every
promotion step is a separate authenticated, idempotent transition with durable
evidence and an outbox event.

```text
verified response
      |
      v
policy + provenance + secret/PII scanner
      | rejected --------------------> content-free rejection audit
      v
durable intake: queued
      |
      | separate worker request
      v
LearningCandidate: candidate
      |
      v
training -> evaluating -> canary-1 -> canary-10 -> canary-50 -> production
                         \__________________________________________/
                                      explicit rollback
```

## Eligibility policy

An intake enters `queued` only when all of the following are true:

- consent is `explicit`, `contractual`, or `public-permitted`;
- license is `permitted`;
- retention is `training-approved`;
- the source response is `completed`;
- the quality and deterministic verifier verdicts are `passed`;
- provenance contains an actor and policy version;
- canonical artifact hashes, when present, use `sha256:<64 lowercase hex>`;
- no secret or supported PII pattern is detected.

Anything else becomes a `rejected` intake audit. Rejected intake rows contain
no request, response, tool-call, prompt, or matched value. They retain only
normalized policy/provenance, scanner counts and a rejection code. Redaction is
defense in depth; it does not turn detected secret/PII content into trainable
content.

The v1 scanner detects sensitive fields and common credential formats,
authorization headers, private keys, token-bearing URLs, email addresses,
Russian phone/passport/SNILS shapes, and payment-card-shaped values. This is a
bounded deterministic scanner, not a claim of exhaustive PII detection.

## Durable records

The Python compatibility runtime stores FormulaLM records in the same SQLite
database selected by `KOLIBRI_EXECUTION_DB_PATH`, but in isolated tables:

- `formulalm_intakes` — idempotent intake queue and content-free rejections;
- `formulalm_candidates` — sanitized candidates and current promotion state;
- `formulalm_transition_events` — immutable promotion/rollback evidence;
- `formulalm_outbox` — pending events for the later JetStream publisher.

This preserves the V1 IDs, state semantics, outbox boundary and restart
durability while PostgreSQL/NATS/S3 become authoritative. It does not make
SQLite the target production architecture.

## Authenticated API

All routes are mounted on the existing authenticated execution router and fail
closed without a configured bearer credential:

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/v1/learning/status` | Queue/candidate aggregate and safety flags |
| `GET` | `/v1/learning/intakes` | List intake audits; optional `status` filter |
| `GET` | `/v1/learning/intakes/{id}` | Inspect one intake audit |
| `POST` | `/v1/learning/queue/process` | Separate worker claims queued traces and creates candidates |
| `POST` | `/v1/learning/candidates` | Compatibility manual sanitized-candidate intake |
| `GET` | `/v1/learning/candidates` | List compatibility and durable candidates |
| `GET` | `/v1/learning/candidates/{id}` | Inspect one candidate |
| `POST` | `/v1/learning/candidates/{id}/transitions` | Explicit evidence-gated transition |
| `GET` | `/v1/learning/candidates/{id}/transitions` | Immutable transition history |

`/v1/responses` accepts an optional `learning` policy. The safe default is
`consent=unknown`, `license=unknown`, `retention_class=project`; therefore an
ordinary request is inference-only and creates no learning candidate.

Example eligible policy:

```json
{
  "consent": "explicit",
  "license": "permitted",
  "retention_class": "training-approved",
  "data_classification": "internal",
  "capability": "code.review"
}
```

## Promotion and rollback gates

The legal transitions are fixed:

```text
candidate -> training -> evaluating -> canary-1 -> canary-10 -> canary-50 -> production
    |            |           |             |            |            |
    +----------> rejected    +-------------+------------+----------> rolled-back
```

Required evidence accumulates by gate:

- `training`: dataset SHA-256 and training run ID;
- `evaluating`: model artifact SHA-256 and passed training verdict;
- `canary-1`: passed independent eval council and eval report SHA-256;
- `canary-10` / `canary-50`: passed canary report and retained external fallback;
- `production`: passed canary, release-manifest SHA-256, retained external
  fallback and explicit owner approval ID;
- `rolled-back`: reason, rollback target and retained external fallback.

Direct `candidate -> production`, missing-gate transitions, and transition
idempotency conflicts return a conflict/policy error. Neither queue processing
nor status reads can advance promotion state. Candidate records always carry
`auto_promote=false`, `request_path_training=false`, and
`production_weight_mutation=false`.

## Verification scope

Focused tests in `tests/test_formulalm_learning_boundary.py` prove:

- response tap versus separate queue processing;
- restart durability and processing idempotency;
- secret, PII, denied-consent and negative-license rejection;
- no rejected trace content in FormulaLM tables;
- bearer-auth failure closed;
- illegal direct production rejection;
- required training/eval/canary/owner gates;
- durable explicit rollback;
- no synchronous weight mutation or automatic promotion flags.

These tests prove the compatibility boundary implementation only. A real
trainer, independent eval service, signed canary release and production model
promotion remain separate protected work.
