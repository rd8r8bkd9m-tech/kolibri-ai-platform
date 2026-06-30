# Estimate API contract - main node

Task: `KOL-REMOTE-SERVER-TASK-20260629T1603-005-MAIN-ESTIMATE`

## Implemented contract

The deterministic estimate engine is now exposed through FastAPI endpoints:

- `GET /api/estimates/contract` returns endpoint names, JSON schemas, canonical schema version, and claim constraints.
- `POST /api/estimates/generate` accepts `prompt`, `client_name`, `object_address`, `currency`, and optional `claim`.
- `POST /api/estimates/edit` accepts a generated `estimate`, `expected_canonical_hash`, a partial `edits` patch, and optional `claim`.

Generate returns an estimate plus:

- `canonical_json`
- `canonical_hash`
- `contract.schema_version`
- `contract.claim_constraints`

Edit-after-generate flow:

1. Client calls `POST /api/estimates/generate`.
2. Client stores returned `estimate` and `canonical_hash`.
3. Client calls `POST /api/estimates/edit` with the stored estimate, `expected_canonical_hash`, and edits.
4. Server recalculates the submitted estimate and compares canonical hashes before applying edits.
5. Hash mismatch returns HTTP `409` with `canonical_hash_conflict`.
6. Successful edit returns the new `canonical_hash` and `previous_canonical_hash`.

## Canonical JSON/hash

Canonical schema version: `kolibri.estimate.v1`.

Canonical JSON uses UTF-8 JSON with sorted keys and compact separators. The hash is returned as `sha256:<hex>`.

The canonical payload includes the estimate content, deterministic calculation lines, totals, rates, and formula. Volatile transport/runtime fields are excluded:

- `created_at`
- `updated_at`
- `captured_at`
- `calculated_at`
- `calculation_audit`

Prompt-generated estimates now derive `estimate_id` from normalized prompt/client/address/currency input so equivalent generate calls produce stable IDs and canonical hashes.

## 98-99% claim constraints

The API contract does not treat deterministic recalculation as a price-accuracy warranty.

Any `claim.percent >= 98.00` is rejected unless all of these are present:

- `basis: "external_audit"`
- `sample_size >= 100`
- non-empty `evidence_reference`

This allows claims about deterministic recalculation, rounding, canonical JSON, hashes, and edit conflict checks while preventing unsupported 98-99% accuracy/completeness claims.

## Changed files

- `backend/estimate_engine.py`
- `backend/estimate_api.py`
- `backend/main.py`
- `backend/tests/test_estimate_document_pdf_engines.py`
- `docs/agent-work/generated/remote-server-transfer-20260629T1603/estimate-api-contract-main.md`

## Verification commands

- `python3 -m pytest backend/tests/test_estimate_document_pdf_engines.py -q`
  - Result: not runnable in this environment because `pytest` is not installed: `No module named pytest`.
- `python3 -m compileall backend/estimate_engine.py backend/estimate_api.py backend/main.py backend/tests/test_estimate_document_pdf_engines.py`
  - Result: passed.
- Direct FastAPI/engine smoke command using `python3 - <<'PY' ... PY`
  - Covered stable generated estimate IDs, stable canonical hashes, volatile key exclusion, `GET /api/estimates/contract`, generate, edit, hash conflict, and unsupported 98.50% claim rejection.
  - Result: `estimate contract smoke ok`.

## Result reference and fallback

Artifact result reference: `docs/agent-work/generated/remote-server-transfer-20260629T1603/estimate-api-contract-main.md`.

Control Plane completion: succeeded; task state is `completed` and `result_reference` is set to this artifact path.

Telegram delivery was not required for this code task; this artifact is the fallback agent-message/report for the Control Plane transfer.

## Risks and follow-ups

- `pytest` is absent from the runtime image, so the checked-in pytest tests were verified through an equivalent direct smoke script instead of the pytest runner.
- Estimate edits currently replace full `sections` when supplied; item-level JSON Patch operations can be added later if the UI needs granular conflict handling.
