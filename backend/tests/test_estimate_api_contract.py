from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routes_v1 import router


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_estimate_contract_endpoint_exposes_schema_and_claim_constraints():
    response = make_client().get("/api/v1/estimates/contract")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "kolibri.estimate.v1"
    assert body["generate_request_schema"]["properties"]["prompt"]["minLength"] == 1
    assert body["canonical_hash"]["algorithm"] == "sha256"
    assert body["claim_constraints"]["requested_claim"] == "98-99%"
    assert body["claim_constraints"]["allowed"] is False


def test_generate_and_recalculate_estimate_contract_flow():
    client = make_client()
    generated = client.post(
        "/api/v1/estimates/generate",
        json={"prompt": "Нужна смета на ремонт кухни 12 м2", "client_name": "Иван"},
    )

    assert generated.status_code == 200
    generated_body = generated.json()
    assert generated_body["schema_version"] == "kolibri.estimate.v1"
    assert len(generated_body["canonical_hash"]) == 64
    assert len(generated_body["calculation_hash"]) == 64
    canonical_payload = json.loads(generated_body["canonical_json"])
    assert canonical_payload["schema_version"] == "kolibri.estimate.v1"
    assert canonical_payload["estimate"]["client_name"] == "Иван"
    assert generated_body["claim_constraints"]["allowed"] is False

    edited_estimate = generated_body["estimate"]
    edited_estimate["sections"][0]["items"][0]["material_unit_price"] = "99.00"
    recalculated = client.post(
        "/api/v1/estimates/recalculate",
        json={"estimate": edited_estimate, "base_canonical_hash": generated_body["canonical_hash"]},
    )

    assert recalculated.status_code == 200
    recalculated_body = recalculated.json()
    assert recalculated_body["canonical_hash"] != generated_body["canonical_hash"]
    assert recalculated_body["edit"]["base_canonical_hash"] == generated_body["canonical_hash"]
    assert recalculated_body["edit"]["hash_changed"] is True
    assert recalculated_body["estimate"]["totals"]["grand_total"] > generated_body["estimate"]["totals"]["grand_total"]
