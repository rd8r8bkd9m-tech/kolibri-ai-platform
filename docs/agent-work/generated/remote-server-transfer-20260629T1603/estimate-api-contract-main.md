# Estimate API contract: Main server

Task: `KOL-REMOTE-SERVER-TASK-20260629T1603-005-MAIN-ESTIMATE-DELIVERABLE-RETRY`

Result reference: `docs/agent-work/generated/remote-server-transfer-20260629T1603/estimate-api-contract-main.md`

## Scope

The deterministic estimate engine is now exposed through a versioned API contract on the Main backend. The contract connects these code paths:

- `backend/estimate_engine.py`: deterministic line normalization, totals, audit fingerprint, canonical JSON/hash helpers, and claim constraints.
- `backend/routes_v1.py`: API request/response schemas and estimate endpoints.
- `backend/tests/test_estimate_api_contract.py`: endpoint-level contract regression tests.
- `backend/tests/test_estimate_document_pdf_engines.py`: engine-level canonical hash regression tests.

Schema version: `kolibri.estimate.v1`.

## Endpoints

### `GET /api/v1/estimates/contract`

Returns the runtime contract metadata:

- `schema_version`
- `generate_request_schema`
- `edit_request_schema`
- `response_schema`
- `claim_constraints`
- `canonical_hash` rules

This endpoint is intended for clients, Mini App code, and remote agents that need to bind to the current estimate input/output shape without reading Python internals.

### `POST /api/v1/estimates/generate`

Request schema:

```json
{
  "prompt": "Нужна смета на ремонт кухни 12 м2",
  "client_name": "Иван",
  "object_address": "optional",
  "currency": "RUB",
  "overhead_rate": "7.00",
  "tax_rate": "0.00"
}
```

Required field: `prompt`.

The endpoint calls `create_estimate_from_prompt`, applies optional contract overrides, recalculates with the deterministic engine, and returns the contract envelope.

### `POST /api/v1/estimates/recalculate`

Request schema:

```json
{
  "estimate": {
    "estimate_id": "EST-...",
    "title": "Смета на ремонт кухни",
    "client_name": "Иван",
    "object_address": "Адрес объекта не указан",
    "currency": "RUB",
    "sections": []
  },
  "base_canonical_hash": "optional 64-char sha256 from a previous response"
}
```

The endpoint accepts a full edited estimate payload, validates it through the `Estimate` Pydantic model, recalculates all derived totals, and returns a new envelope. If `base_canonical_hash` is provided, the response includes:

```json
{
  "edit": {
    "base_canonical_hash": "previous hash",
    "hash_changed": true
  }
}
```

The current implementation is stateless: `base_canonical_hash` is edit lineage metadata, not a persistence-layer optimistic lock.

## Response envelope

Both generate and recalculate return:

```json
{
  "schema_version": "kolibri.estimate.v1",
  "estimate": {},
  "canonical_json": "{}",
  "canonical_hash": "64-char sha256",
  "calculation_hash": "64-char sha256",
  "claim_constraints": {},
  "edit": null
}
```

`estimate` is the normalized `Estimate` model, including recalculated `totals` and `calculation_audit`.

`calculation_hash` is the deterministic audit hash for arithmetic totals.

`canonical_hash` is the SHA-256 hash of `canonical_json`.

## Canonical JSON and hash

Canonical JSON is serialized as UTF-8 with:

- `ensure_ascii=false`
- `sort_keys=true`
- compact separators `(",", ":")`
- `schema_version=kolibri.estimate.v1`

The canonical payload excludes volatile runtime fields:

- `estimate.created_at`
- `estimate.updated_at`
- `estimate.sections[].items[].provenance.captured_at`
- `estimate.calculation_audit[].calculated_at`

The canonical payload keeps estimate identity, section/item economics, provenance source/label/confidence, deterministic totals, and non-volatile audit data. This means:

- Recalculating the same estimate payload produces the same `canonical_hash`.
- Editing a line quantity or price produces a different `canonical_hash`.
- Repeating prompt generation may produce a different `canonical_hash` because a new estimate identity is created.

## Edit-after-generate flow

1. Client calls `POST /api/v1/estimates/generate`.
2. Client stores `estimate` and `canonical_hash`.
3. User edits line items, rates, notes, sections, client fields, or address locally.
4. Client calls `POST /api/v1/estimates/recalculate` with the full edited `estimate` and the previous `base_canonical_hash`.
5. Server validates the schema, recalculates totals, emits a new `calculation_hash`, new `canonical_json`, and new `canonical_hash`.
6. Client compares `edit.hash_changed` and stores the returned normalized estimate as the new base.

Clients must treat totals from local UI edits as provisional until the server returns the deterministic recalculation envelope.

## 98-99% claim constraints

The API returns `claim_constraints.allowed=false` for the requested `98-99%` claim.

Allowed public claim:

`Детерминированный пересчёт строк сметы с воспроизводимым аудит-хешем.`

The API must not claim 98-99% estimate accuracy unless separate product evidence exists:

- signed measurement or BIM/plan import with units
- versioned price book with source, region, and capture time
- rounding, tax, and overhead rules
- validation sample comparing planned and actual closed estimates
- separate metrics for arithmetic reproducibility and commercial accuracy

This protects the product from conflating deterministic arithmetic with market-price accuracy.

## Verification

Executed in this workspace:

```bash
python3 -m compileall backend/estimate_engine.py backend/routes_v1.py backend/tests/test_estimate_api_contract.py backend/tests/test_estimate_document_pdf_engines.py
PYTHONPATH=backend python3 - <<'PY'
from estimate_engine import canonical_estimate_hash, canonical_estimate_json, create_estimate_from_prompt, normalize_estimate_payload
estimate = create_estimate_from_prompt('Нужна смета на ремонт кухни 12 м2', client_name='Иван')
first_hash = canonical_estimate_hash(estimate)
payload = estimate.model_dump(mode='json')
payload['updated_at'] = '2030-01-01T00:00:00+00:00'
payload['calculation_audit'][-1]['calculated_at'] = '2030-01-01T00:00:00+00:00'
payload['sections'][0]['items'][0]['provenance']['captured_at'] = '2030-01-01T00:00:00+00:00'
normalized = normalize_estimate_payload(payload)
assert canonical_estimate_hash(normalized) == first_hash
canonical_json = canonical_estimate_json(normalized)
assert 'calculated_at' not in canonical_json
assert 'captured_at' not in canonical_json
edited_payload = estimate.model_dump(mode='json')
edited_payload['sections'][0]['items'][0]['material_unit_price'] = '99.00'
edited = normalize_estimate_payload(edited_payload)
assert canonical_estimate_hash(edited) != first_hash
assert edited.totals.grand_total > estimate.totals.grand_total
PY
PYTHONPATH=backend python3 - <<'PY'
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routes_v1 import router
app = FastAPI()
app.include_router(router)
client = TestClient(app)
contract = client.get('/api/v1/estimates/contract')
generated = client.post('/api/v1/estimates/generate', json={'prompt': 'Нужна смета на ремонт кухни 12 м2', 'client_name': 'Иван'})
body = generated.json()
edited = body['estimate']
edited['sections'][0]['items'][0]['material_unit_price'] = '99.00'
recalculated = client.post('/api/v1/estimates/recalculate', json={'estimate': edited, 'base_canonical_hash': body['canonical_hash']})
assert contract.status_code == 200
assert generated.status_code == 200
assert recalculated.status_code == 200
assert body['claim_constraints']['allowed'] is False
assert recalculated.json()['edit']['hash_changed'] is True
PY
```

`python3 -m pytest` was not executed because this runtime does not have `pytest` installed (`No module named pytest`). The repo does not list pytest in `backend/requirements.txt`.
