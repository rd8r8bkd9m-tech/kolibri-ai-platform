# Estimate API Contract Main

Task id: `KOL-REMOTE-SERVER-TASK-20260629T1603-005B-MAIN-ESTIMATE-IMPLEMENTATION`

Result reference: `docs/agent-work/generated/remote-server-transfer-20260629T1603/estimate-api-contract-main.md`

## Implemented Scope

- Connected the deterministic estimate engine to a typed API contract in `backend/estimate_engine.py`.
- Added v1 FastAPI endpoints in `backend/routes_v1.py`:
  - `GET /api/v1/estimate/schema`
  - `POST /api/v1/estimate/generate`
  - `POST /api/v1/estimate/edit`
- Added regression tests in `backend/tests/test_estimate_api_contract.py`.
- This file is also the fallback agent-message/report artifact if Telegram delivery is unavailable.

## Input Schema

`EstimateGenerateRequest`:

- `prompt`: required string, 1..4000 chars, trimmed before validation.
- `client_name`: optional string, default `Клиент`, trimmed before validation.
- `object_address`: optional string, default `Адрес объекта не указан`, trimmed before validation.
- `currency`: optional ISO-style 3-letter code, default `RUB`, trimmed and uppercased.
- `claim_accuracy_percent`: optional decimal, default `98.00`, constrained to inclusive range `98.00..99.00`.

`EstimateEditRequest`:

- `estimate`: previously generated or normalized `Estimate` payload.
- `base_canonical_hash`: optional 64-char lowercase sha256 hex. When supplied, edit returns `409` if the submitted estimate hash does not match.
- `edits`: 1..100 JSON-Pointer operations with `op` in `add`, `replace`, `remove`.
- `claim_accuracy_percent`: same inclusive `98.00..99.00` constraint.

## Canonical JSON And Hash

Canonicalization uses compact sorted JSON:

`json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)`

Hash algorithm: `sha256(canonical_json.encode("utf-8"))`.

Canonical estimate payload excludes volatile or derived fields:

- `created_at`
- `updated_at`
- `calculation_audit`
- `provenance.captured_at`

It includes deterministic semantic fields:

- `estimate_id`
- header fields
- ordered sections/items
- normalized two-decimal quantities, rates, line totals, and grand totals
- provenance source, label, and confidence

Observed smoke hashes:

- Generated estimate canonical hash: `03b38164d76842940db0c03088a6de1666f292c18d18d60af49d6a93c076b054`
- Edited estimate canonical hash: `46e198309a91d3ef27c9a87ac50e9cfaa4a31e58f4c637566079deb0ada4a14f`

## Edit-After-Generate Flow

1. Client calls `POST /api/v1/estimate/generate`.
2. API returns `estimate`, `input_hash`, `canonical_json`, and `canonical_hash`.
3. Client sends the estimate to `POST /api/v1/estimate/edit` with `base_canonical_hash`.
4. API recomputes the submitted estimate hash before applying edits.
5. If `base_canonical_hash` mismatches, API returns `409`.
6. If it matches, API applies allowed JSON-Pointer edits, recalculates totals, and returns a new `canonical_hash` plus `previous_hash`.

Editable roots are limited to:

- `title`
- `client_name`
- `object_address`
- `currency`
- `sections`
- `overhead_rate`
- `tax_rate`

Immutable or derived fields cannot be edited directly:

- `estimate_id`
- `totals`
- `calculation_audit`
- `created_at`
- `updated_at`

## Claim Constraints

The API enforces the 98-99 claim range as an input constraint:

- Minimum: `98.00`
- Maximum: `99.00`
- Out-of-range claims return request validation error `422`.

Claim scope is intentionally narrow: deterministic arithmetic and canonical hash integrity only. It is not a guarantee of market price accuracy, external supplier pricing, or legal/financial correctness. Human review remains required.

## Verification Commands

Attempted full pytest:

```bash
pytest backend/tests/test_estimate_api_contract.py backend/tests/test_estimate_document_pdf_engines.py
```

Result: failed because `pytest` command is not installed in the execution environment.

Attempted module pytest:

```bash
python3 -m pytest backend/tests/test_estimate_api_contract.py backend/tests/test_estimate_document_pdf_engines.py
```

Result: failed because Python module `pytest` is not installed.

Passed compile check:

```bash
python3 -m py_compile backend/estimate_engine.py backend/routes_v1.py backend/tests/test_estimate_api_contract.py
```

Passed direct FastAPI route smoke:

```bash
python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routes_v1 import router
app = FastAPI()
app.include_router(router)
client = TestClient(app)
schema = client.get('/api/v1/estimate/schema')
assert schema.status_code == 200, schema.text
generated_response = client.post('/api/v1/estimate/generate', json={'prompt': ' Repair apartment 12 m2 ', 'client_name': ' Client A ', 'currency': ' rub '})
assert generated_response.status_code == 200, generated_response.text
generated = generated_response.json()
assert generated['estimate']['currency'] == 'RUB'
edit_response = client.post('/api/v1/estimate/edit', json={'estimate': generated['estimate'], 'base_canonical_hash': generated['canonical_hash'], 'edits': [{'op': 'replace', 'path': '/sections/0/items/0/quantity', 'value': '24'}], 'claim_accuracy_percent': '99.00'})
assert edit_response.status_code == 200, edit_response.text
conflict_response = client.post('/api/v1/estimate/edit', json={'estimate': generated['estimate'], 'base_canonical_hash': '0' * 64, 'edits': [{'op': 'replace', 'path': '/client_name', 'value': 'Other'}]})
assert conflict_response.status_code == 409, conflict_response.text
bad_claim = client.post('/api/v1/estimate/generate', json={'prompt': 'Repair apartment 12 m2', 'claim_accuracy_percent': '99.01'})
assert bad_claim.status_code == 422, bad_claim.text
bad_null = client.post('/api/v1/estimate/generate', json={'prompt': None})
assert bad_null.status_code == 422, bad_null.text
print(generated['canonical_hash'])
print(edit_response.json()['canonical_hash'])
PY
```

Result: passed.

Passed whitespace check:

```bash
git diff --check
```

Result: passed.

## Risks And Follow-Ups

- `pytest` is unavailable in this runtime; the new pytest coverage is committed-ready but was not run by pytest here.
- The API is stateless and does not persist estimate versions; clients must keep the returned estimate and `canonical_hash`.
- Canonical hash intentionally ignores volatile timestamps. If downstream consumers require timestamp integrity, add a separate signed envelope hash instead of changing the estimate canonical hash.
