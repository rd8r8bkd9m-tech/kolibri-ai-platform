from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from estimate_engine import EstimateGenerateRequest, create_estimate_api_from_prompt
from routes_v1 import router


def api_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_canonical_hash_is_stable_for_same_generate_input():
    request = EstimateGenerateRequest(
        prompt="Repair apartment 12 m2",
        client_name="Client A",
        object_address="Main st",
        currency="rub",
        claim_accuracy_percent="98.50",
    )

    first = create_estimate_api_from_prompt(request)
    second = create_estimate_api_from_prompt(request)

    assert first.input_hash == second.input_hash
    assert first.canonical_hash == second.canonical_hash
    assert first.estimate.estimate_id == second.estimate.estimate_id
    assert first.claim_accuracy_percent == Decimal("98.50")

    payload = json.loads(first.canonical_json)
    assert payload["estimate"]["currency"] == "RUB"
    assert "created_at" not in payload["estimate"]
    assert "updated_at" not in payload["estimate"]
    provenance = payload["estimate"]["sections"][0]["items"][0]["provenance"]
    assert "captured_at" not in provenance


def test_estimate_schema_endpoint_exposes_input_and_claim_contract():
    response = api_client().get("/api/v1/estimate/schema")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "estimate-api-contract/v1"
    assert payload["hash_algorithm"] == "sha256"
    assert payload["claim_constraints"]["allowed_accuracy_percent_min"] == "98.00"
    assert payload["claim_constraints"]["allowed_accuracy_percent_max"] == "99.00"
    assert "EstimateGenerateRequest" in payload["schemas"]
    assert payload["endpoints"]["edit"] == "POST /api/v1/estimate/edit"


def test_edit_after_generate_endpoint_recalculates_hash_and_enforces_base_hash():
    client = api_client()
    generated_response = client.post(
        "/api/v1/estimate/generate",
        json={"prompt": "Repair apartment 12 m2", "client_name": "Client A"},
    )
    assert generated_response.status_code == 200
    generated = generated_response.json()
    base_total = Decimal(generated["estimate"]["totals"]["grand_total"])

    edit_response = client.post(
        "/api/v1/estimate/edit",
        json={
            "estimate": generated["estimate"],
            "base_canonical_hash": generated["canonical_hash"],
            "edits": [{"op": "replace", "path": "/sections/0/items/0/quantity", "value": "24"}],
            "claim_accuracy_percent": "99.00",
        },
    )

    assert edit_response.status_code == 200
    edited = edit_response.json()
    assert edited["previous_hash"] == generated["canonical_hash"]
    assert edited["canonical_hash"] != generated["canonical_hash"]
    assert Decimal(edited["estimate"]["totals"]["grand_total"]) > base_total
    assert edited["estimate"]["sections"][0]["items"][0]["quantity"] == "24.00"
    assert edited["edit_audit"] == [{"op": "replace", "path": "/sections/0/items/0/quantity"}]

    conflict_response = client.post(
        "/api/v1/estimate/edit",
        json={
            "estimate": generated["estimate"],
            "base_canonical_hash": "0" * 64,
            "edits": [{"op": "replace", "path": "/client_name", "value": "Other Client"}],
        },
    )
    assert conflict_response.status_code == 409


@pytest.mark.parametrize("claim", ["97.99", "99.01"])
def test_estimate_generate_rejects_claims_outside_98_99(claim: str):
    response = api_client().post(
        "/api/v1/estimate/generate",
        json={"prompt": "Repair apartment 12 m2", "claim_accuracy_percent": claim},
    )

    assert response.status_code == 422
