# Estimate API contract - Main server

Task: `KOL-REMOTE-SERVER-TASK-20260629T1603-005-MAIN-ESTIMATE-DELIVERABLE-RETRY`

Result reference: `docs/agent-work/generated/remote-server-transfer-20260629T1603/estimate-api-contract-main.md`

## Implemented contract

The deterministic estimate engine is bound to a FastAPI contract on the Main backend:

- `backend/estimate_engine.py` provides deterministic recalculation, canonical JSON/hash helpers, deterministic generated estimate IDs, and audit fingerprints.
- `backend/estimate_api.py` exposes the estimate contract endpoints and validates unsupported 98-99% accuracy claims.
- `backend/main.py` mounts the estimate API router before the existing v1 router.
- `backend/tests/test_estimate_document_pdf_engines.py` covers engine determinism, canonical hashes, edit conflict flow, and claim rejection.

Schema version: `kolibri.estimate.v1`.

## Endpoints

### `GET /api/estimates/contract`

Returns endpoint names, input JSON schemas, canonical schema version, and claim constraints.

### `POST /api/estimates/generate`

Accepts:

```json
{
  "prompt": "Нужна смета на ремонт кухни 12 м2",
  "client_name": "Иван",
  "object_address": "Адрес объекта не указан",
  "currency": "RUB",
  "claim": null
}
```

Returns an estimate plus `canonical_json`, `canonical_hash`, and `contract.claim_constraints`.

### `POST /api/estimates/edit`

Accepts a generated estimate, the previous `expected_canonical_hash`, a partial `edits` patch, and optional `claim`.

```json
{
  "estimate": {},
  "expected_canonical_hash": "sha256:<previous>",
  "edits": {
    "overhead_rate": "12.00"
  },
  "claim": null
}
```

The server recalculates the submitted estimate and compares hashes before applying edits. A mismatch returns HTTP `409` with `canonical_hash_conflict`; a successful edit returns the new `canonical_hash` and `previous_canonical_hash`.

## Canonical JSON/hash

Canonical JSON uses UTF-8 JSON with sorted keys and compact separators. Hashes are returned as `sha256:<hex>`.

The canonical payload includes estimate content, deterministic calculation lines, totals, rates, and formula. Volatile runtime fields are excluded:

- `created_at`
- `updated_at`
- `captured_at`
- `calculated_at`
- `calculation_audit`

Prompt-generated estimates derive `estimate_id` from normalized prompt, client, address, and currency input, so equivalent generate calls produce stable IDs and canonical hashes.

Retry refinement: `estimate_canonical_payload` recalculates a deep copy, so creating canonical JSON/hash does not mutate runtime timestamps on the caller's estimate object.

## Edit-after-generate flow

1. Client calls `POST /api/estimates/generate`.
2. Client stores returned `estimate` and `canonical_hash`.
3. User edits fields locally.
4. Client calls `POST /api/estimates/edit` with the stored estimate, `expected_canonical_hash`, and patch object.
5. Server recalculates and checks the submitted base estimate hash.
6. If the base hash matches, server applies edits, recalculates, and returns a new canonical envelope.
7. If the base hash does not match, server returns HTTP `409` and does not apply the patch.

Clients must treat UI-side totals as provisional until the server returns the deterministic recalculation envelope.

## 98-99% claim constraints

The API contract does not treat deterministic recalculation as a price-accuracy warranty.

Any `claim.percent >= 98.00` is rejected unless all of these are present:

- `basis: "external_audit"`
- `sample_size >= 100`
- non-empty `evidence_reference`

Allowed claims are limited to deterministic recalculation, rounding, canonical JSON, hashes, and edit conflict checks unless external audit evidence is supplied.

## Fallback report

Telegram delivery was not used for this code task. This artifact is the fallback agent-message/report and can be used as the Control Plane `result_reference`.

## Verification commands

Executed in this workspace:

```bash
python3 -m compileall backend/estimate_engine.py backend/estimate_api.py backend/main.py backend/tests/test_estimate_document_pdf_engines.py
PYTHONPATH=backend python3 - <<'PY'
from estimate_engine import create_estimate_from_prompt, estimate_canonical_hash, estimate_canonical_json, normalize_estimate_payload
estimate = create_estimate_from_prompt('Нужна смета на ремонт кухни 12 м2', client_name='Иван')
repeated = create_estimate_from_prompt('Нужна смета на ремонт кухни 12 м2', client_name='Иван')
assert estimate.estimate_id == repeated.estimate_id
assert estimate_canonical_hash(estimate) == estimate_canonical_hash(repeated)
updated_at = estimate.updated_at
calculated_at = estimate.calculation_audit[-1]['calculated_at']
first_hash = estimate_canonical_hash(estimate)
assert estimate.updated_at == updated_at
assert estimate.calculation_audit[-1]['calculated_at'] == calculated_at
assert 'captured_at' not in estimate_canonical_json(estimate)
payload = estimate.model_dump(mode='json')
payload['sections'][0]['items'][0]['material_unit_price'] = '99.00'
edited = normalize_estimate_payload(payload)
assert estimate_canonical_hash(edited) != first_hash
PY
PYTHONPATH=backend python3 - <<'PY'
from fastapi.testclient import TestClient
from main import app
client = TestClient(app)
contract = client.get('/api/estimates/contract')
generated = client.post('/api/estimates/generate', json={'prompt': 'Нужна смета на ремонт кухни 12 м2', 'client_name': 'Иван'})
body = generated.json()
edited = client.post('/api/estimates/edit', json={'estimate': body['estimate'], 'expected_canonical_hash': body['canonical_hash'], 'edits': {'overhead_rate': '12.00'}})
conflict = client.post('/api/estimates/edit', json={'estimate': body['estimate'], 'expected_canonical_hash': 'sha256:deadbeef', 'edits': {'overhead_rate': '15.00'}})
claim = client.post('/api/estimates/generate', json={'prompt': 'Смета на ремонт квартиры 20 м2', 'claim': {'percent': '98.50', 'basis': 'manual'}})
assert contract.status_code == 200
assert generated.status_code == 200
assert edited.status_code == 200
assert conflict.status_code == 409
assert claim.status_code == 422
assert body['canonical_hash'].startswith('sha256:')
assert edited.json()['previous_canonical_hash'] == body['canonical_hash']
PY
git diff --check
```

`python3 -m pytest` was not executed because this runtime does not have `pytest` installed (`No module named pytest`). The repo does not list pytest in `backend/requirements.txt`.
