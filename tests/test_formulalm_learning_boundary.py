import hashlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
AUTH_HEADERS = {"Authorization": "Bearer formulalm-test-key"}


def load_execution_api():
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    spec = importlib.util.spec_from_file_location(
        f"execution_api_formulalm_{hashlib.sha256(str(BACKEND).encode()).hexdigest()[:8]}",
        BACKEND / "execution_api.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class VerifiedGateway:
    def generate(self, input_value, instructions, response_id, **kwargs):
        del instructions, response_id, kwargs
        text = f"Verified answer for {input_value}"
        evidence = [{
            "type": "provider_execution",
            "provider": "test-provider",
            "provider_model": "test-model",
            "exit_code": 0,
            "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "output_bytes": len(text.encode()),
            "completion_signal": "non_empty_assistant_output",
        }]
        return SimpleNamespace(status="completed", text=text, technical={
            "selected_provider": "test-provider",
            "fallback_candidates": [],
            "attempts": [{
                "attempt": 1,
                "provider": "test-provider",
                "status": "succeeded",
                "evidence": evidence,
            }],
            "fallback_used": False,
            "evidence": evidence,
        })


def make_client(tmp_path):
    execution = load_execution_api()
    db_path = tmp_path / "execution.db"
    execution.configure_execution_store(db_path)
    execution.configure_execution_auth(["formulalm-test-key"])
    import capability_gateway
    import provider_gateway

    provider_gateway.configure_provider_gateway(VerifiedGateway())
    capability_gateway.configure_capability_gateway(
        capability_gateway.CapabilityGateway([], cache_ttl=0, include_packaged_registry=False)
    )
    app = FastAPI()
    app.include_router(execution.router)
    return execution, db_path, app, TestClient(app, headers=AUTH_HEADERS)


def eligible_request(idempotency_key="eligible-trace", input_value="safe trace"):
    return {
        "idempotency_key": idempotency_key,
        "model": "kolibri",
        "input": input_value,
        "learning": {
            "consent": "explicit",
            "license": "permitted",
            "retention_class": "training-approved",
            "data_classification": "internal",
            "capability": "general.reasoning",
        },
    }


def test_response_tap_only_enqueues_then_worker_creates_durable_candidate(tmp_path):
    execution, db_path, _, client = make_client(tmp_path)

    response = client.post("/v1/responses", json=eligible_request())
    assert response.status_code == 201
    body = response.json()
    tap = body["technical"]["learning_tap"]
    assert body["status"] == "completed"
    assert tap["status"] == "queued"
    assert tap["async_queue"] is True
    assert tap["auto_promote"] is False
    assert tap["request_path_training"] is False
    assert tap["production_weight_mutation"] is False

    queued = client.get("/v1/learning/intakes?status=queued").json()["data"]
    assert len(queued) == 1
    assert queued[0]["source_response_id"] == body["id"]
    assert queued[0]["content_persisted"] is True
    assert client.get("/v1/learning/candidates").json()["data"] == []

    # A new store object sees the same durable intake before any worker runs.
    execution.configure_execution_store(db_path)
    assert len(client.get("/v1/learning/intakes?status=queued").json()["data"]) == 1

    processed = client.post(
        "/v1/learning/queue/process",
        json={"worker_id": "formulalm-worker-test", "limit": 10},
    )
    assert processed.status_code == 200
    assert processed.json()["processed_count"] == 1
    candidate = processed.json()["candidates"][0]
    assert candidate["promotion_status"] == "candidate"
    assert candidate["source_trace_id"] == body["id"]
    assert candidate["provenance"]["actor"] == "provider-gateway"
    assert candidate["provenance"]["principal"].startswith("authn:")
    assert candidate["artifact_hashes"][0].startswith("sha256:")
    assert candidate["quality_verdict"] == "passed"
    assert candidate["verifier_verdict"] == "passed"
    assert candidate["sanitization"] == {
        "status": "passed",
        "redacted_fields": [],
        "scanner_version": "kolibri.formulalm-scanner.v1",
        "reason": None,
    }
    assert candidate["auto_promote"] is False
    assert candidate["production_weight_mutation"] is False

    # Processing is idempotent: the accepted intake cannot create a duplicate.
    again = client.post(
        "/v1/learning/queue/process",
        json={"worker_id": "formulalm-worker-test", "limit": 10},
    ).json()
    assert again["processed_count"] == 0
    assert len(client.get("/v1/learning/candidates").json()["data"]) == 1


def test_secret_pii_no_consent_and_negative_license_never_enter_queue(tmp_path):
    _, db_path, _, client = make_client(tmp_path)
    secret = "sk-" + "never-persist-this-123456789"
    email = "private.person@example.com"
    requests = [
        eligible_request("secret-trace", f"use {secret}"),
        eligible_request("pii-trace", f"email {email}"),
        {
            **eligible_request("no-consent", "safe content"),
            "learning": {
                **eligible_request()["learning"],
                "consent": "denied",
            },
        },
        {
            **eligible_request("negative-license", "safe content"),
            "learning": {
                **eligible_request()["learning"],
                "license": "negative",
            },
        },
    ]
    expected = [
        "learning_secret_detected",
        "learning_pii_detected",
        "learning_consent_required",
        "learning_license_not_permitted",
    ]
    for payload, rejection in zip(requests, expected, strict=True):
        result = client.post("/v1/responses", json=payload)
        assert result.status_code == 201
        tap = result.json()["technical"]["learning_tap"]
        assert tap["status"] == "rejected"
        assert tap["rejection_code"] == rejection
        assert tap["async_queue"] is False

    rejected = client.get("/v1/learning/intakes?status=rejected").json()["data"]
    assert len(rejected) == 4
    assert all(item["content_persisted"] is False for item in rejected)
    assert client.post(
        "/v1/learning/queue/process",
        json={"worker_id": "formulalm-worker-test", "limit": 100},
    ).json()["processed_count"] == 0
    assert client.get("/v1/learning/candidates").json()["data"] == []

    manual_pii = client.post("/v1/learning/candidates", json={
        "idempotency_key": "manual-pii",
        "source_response_id": result.json()["id"],
        "kind": "semantic",
        "summary": f"learn {email}",
        "consent": "explicit",
        "license": "permitted",
        "retention_class": "training-approved",
        "data_classification": "private",
    })
    assert manual_pii.status_code == 422
    assert manual_pii.json()["detail"] == "learning candidate PII forbids use"

    # Inspect only FormulaLM tables: rejected raw content is never stored there.
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """SELECT payload, provenance, policy, quality, sanitization
               FROM formulalm_intakes"""
        ).fetchall()
    serialized = json.dumps(rows)
    assert secret not in serialized
    assert email not in serialized


def test_response_and_intake_idempotency_do_not_duplicate_learning_work(tmp_path):
    _, _, _, client = make_client(tmp_path)
    first = client.post("/v1/responses", json=eligible_request("same-response"))
    second = client.post("/v1/responses", json=eligible_request("same-response"))
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(client.get("/v1/learning/intakes").json()["data"]) == 1

    changed = client.post(
        "/v1/responses",
        json=eligible_request("same-response", input_value="different trace"),
    )
    assert changed.status_code == 409
    assert len(client.get("/v1/learning/intakes").json()["data"]) == 1


def test_promotion_requires_explicit_eval_canaries_owner_gate_and_rollback(tmp_path):
    execution, db_path, _, client = make_client(tmp_path)
    response = client.post(
        "/v1/responses", json=eligible_request("promotion-trace")
    ).json()
    candidate = client.post(
        "/v1/learning/queue/process",
        json={"worker_id": "formulalm-worker-test", "limit": 1},
    ).json()["candidates"][0]
    candidate_id = candidate["id"]
    digest = "sha256:" + "a" * 64

    direct_production = client.post(
        f"/v1/learning/candidates/{candidate_id}/transitions",
        json={
            "idempotency_key": "direct-production",
            "to_status": "production",
            "evidence": {},
        },
    )
    assert direct_production.status_code == 409
    assert client.get(f"/v1/learning/candidates/{candidate_id}").json()["promotion_status"] == "candidate"

    missing_training_evidence = client.post(
        f"/v1/learning/candidates/{candidate_id}/transitions",
        json={"idempotency_key": "training-missing", "to_status": "training", "evidence": {}},
    )
    assert missing_training_evidence.status_code == 422

    transitions = [
        ("training", {"dataset_sha256": digest, "training_run_id": "train-1"}),
        ("evaluating", {"model_artifact_sha256": digest, "training_verdict": "passed"}),
        ("canary-1", {
            "eval_report_sha256": digest,
            "independent_eval_verdict": "passed",
            "eval_council_independent": True,
        }),
        ("canary-10", {
            "canary_report_sha256": digest,
            "canary_verdict": "passed",
            "external_fallback_retained": True,
        }),
        ("canary-50", {
            "canary_report_sha256": digest,
            "canary_verdict": "passed",
            "external_fallback_retained": True,
        }),
        ("production", {
            "canary_report_sha256": digest,
            "release_manifest_sha256": digest,
            "canary_verdict": "passed",
            "external_fallback_retained": True,
            "owner_approval_id": "approval-owner-1",
        }),
    ]
    for index, (status, evidence) in enumerate(transitions):
        result = client.post(
            f"/v1/learning/candidates/{candidate_id}/transitions",
            json={
                "idempotency_key": f"promotion-{index}",
                "to_status": status,
                "evidence": evidence,
            },
        )
        assert result.status_code == 200
        assert result.json()["promotion_status"] == status
        assert result.json()["auto_promote"] is False
        assert result.json()["production_weight_mutation"] is False

    rolled_back = client.post(
        f"/v1/learning/candidates/{candidate_id}/transitions",
        json={
            "idempotency_key": "rollback-1",
            "to_status": "rolled-back",
            "reason": "canary regression",
            "evidence": {
                "rollback_target": "external-provider-fallback",
                "external_fallback_retained": True,
            },
        },
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["promotion_status"] == "rolled-back"
    assert rolled_back.json()["rollback"]["target"] == "external-provider-fallback"

    events = client.get(
        f"/v1/learning/candidates/{candidate_id}/transitions"
    ).json()["data"]
    assert [event["to_status"] for event in events] == [
        "training", "evaluating", "canary-1", "canary-10", "canary-50",
        "production", "rolled-back",
    ]

    execution.configure_execution_store(db_path)
    persisted = client.get(f"/v1/learning/candidates/{candidate_id}").json()
    assert persisted["source_response_id"] == response["id"]
    assert persisted["promotion_status"] == "rolled-back"


def test_learning_routes_are_bearer_auth_bound(tmp_path):
    execution, _, app, _ = make_client(tmp_path)
    anonymous = TestClient(app)
    assert anonymous.get("/v1/learning/status").status_code == 401
    assert anonymous.get("/v1/learning/intakes").status_code == 401
    assert anonymous.post(
        "/v1/learning/queue/process",
        json={"worker_id": "anonymous", "limit": 1},
    ).status_code == 401

    execution.configure_execution_auth([])
    assert anonymous.get("/v1/learning/status").status_code == 503


def test_frozen_openapi_lists_authenticated_formula_boundary_routes():
    contract = json.loads(
        (ROOT / "contracts" / "kolibri-os-v1" / "openapi.json").read_text(encoding="utf-8")
    )
    paths = contract["paths"]
    assert {
        "/v1/learning/status",
        "/v1/learning/intakes",
        "/v1/learning/intakes/{intake_id}",
        "/v1/learning/queue/process",
        "/v1/learning/candidates",
        "/v1/learning/candidates/{candidate_id}",
        "/v1/learning/candidates/{candidate_id}/transitions",
    }.issubset(paths)
    assert contract["security"] == [{"BearerAuth": []}]
    transition = paths["/v1/learning/candidates/{candidate_id}/transitions"]["post"]
    assert transition["x-kolibri-auto-promote"] is False
    assert "canary-1" in transition["x-kolibri-state-machine"]
