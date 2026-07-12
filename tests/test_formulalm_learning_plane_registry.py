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
AUTH_HEADERS = {"Authorization": "Bearer formulalm-registry-test-key"}
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64


def load_execution_api():
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    spec = importlib.util.spec_from_file_location(
        f"execution_api_formulalm_registry_{hashlib.sha256(str(BACKEND).encode()).hexdigest()[:8]}",
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
    execution.configure_execution_auth(["formulalm-registry-test-key"])
    import capability_gateway
    import provider_gateway

    provider_gateway.configure_provider_gateway(VerifiedGateway())
    capability_gateway.configure_capability_gateway(
        capability_gateway.CapabilityGateway([], cache_ttl=0, include_packaged_registry=False)
    )
    app = FastAPI()
    app.include_router(execution.router)
    return execution, db_path, app, TestClient(app, headers=AUTH_HEADERS)


def eligible_request(idempotency_key="registry-trace"):
    return {
        "idempotency_key": idempotency_key,
        "model": "kolibri",
        "input": "safe verified trace",
        "learning": {
            "consent": "explicit",
            "license": "permitted",
            "retention_class": "training-approved",
            "data_classification": "internal",
            "capability": "general.reasoning",
        },
    }


def enqueue_fixed_trace(boundary, *, idempotency_key="fixed", trace=None, license_class="permitted"):
    return boundary.enqueue_trace(
        idempotency_key=idempotency_key,
        source_trace_id="trace-stable-001",
        source_response_id="resp-stable-001",
        capability="general.reasoning",
        trace=trace or {
            "request": {"input": "Explain stable hashing"},
            "response": {"status": "completed", "output_text": "Stable answer"},
        },
        provenance={
            "actor": "verified-provider-gateway",
            "principal": "authn:stable-principal",
            "policy_version": "kolibri.formulalm-policy.v1",
        },
        policy={
            "consent": "explicit",
            "license": license_class,
            "retention_class": "training-approved",
            "data_classification": "internal",
        },
        quality={
            "response_status": "completed",
            "quality_verdict": "passed",
            "verifier_verdict": "passed",
            "credit_assignment": {"provider": 1.0, "verifier": 1.0},
        },
        artifact_hashes=[DIGEST_A],
    )


def test_content_addresses_and_provenance_are_stable_while_sensitive_data_is_excluded(tmp_path):
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from formulalm_boundary import FormulaLMBoundary

    boundary_a = FormulaLMBoundary(tmp_path / "a.db")
    boundary_b = FormulaLMBoundary(tmp_path / "b.db")
    for boundary in (boundary_a, boundary_b):
        assert enqueue_fixed_trace(boundary)["status"] == "queued"
        result = boundary.process_pending(worker_id="dataset-builder", limit=1)
        assert result["processed_count"] == 1

    candidate_a = boundary_a.list_candidates()[0]
    candidate_b = boundary_b.list_candidates()[0]
    assert candidate_a["candidate_id"] == candidate_b["candidate_id"]
    assert candidate_a["content_sha256"] == candidate_b["content_sha256"]
    assert candidate_a["provenance"] == candidate_b["provenance"]
    assert candidate_a["candidate_id"].endswith(
        candidate_a["content_sha256"].removeprefix("sha256:")
    )

    dataset_a = boundary_a.create_dataset(
        idempotency_key="dataset-stable",
        candidate_ids=[candidate_a["candidate_id"]],
        capability="general.reasoning",
        builder_id="dataset-builder",
        principal="authn:dataset-principal",
    )
    dataset_b = boundary_b.create_dataset(
        idempotency_key="dataset-stable",
        candidate_ids=[candidate_b["candidate_id"]],
        capability="general.reasoning",
        builder_id="dataset-builder",
        principal="authn:dataset-principal",
    )
    assert dataset_a["dataset_id"] == dataset_b["dataset_id"]
    assert dataset_a["content_sha256"] == dataset_b["content_sha256"]
    assert dataset_a["provenance"] == dataset_b["provenance"]
    assert dataset_a["training_started"] is False
    assert dataset_a["production_weight_mutation"] is False

    synthetic_secret = "sk-synthetic-never-persist-1234567890"
    synthetic_email = "synthetic.private@example.test"
    secret_record = boundary_a.enqueue_trace(
        idempotency_key="secret",
        source_trace_id="trace-secret",
        source_response_id="resp-secret",
        capability="general.reasoning",
        trace={"request": {"input": synthetic_secret}},
        provenance={"actor": "gateway", "policy_version": "v1"},
        policy={
            "consent": "explicit",
            "license": "permitted",
            "retention_class": "training-approved",
        },
        quality={
            "response_status": "completed",
            "quality_verdict": "passed",
            "verifier_verdict": "passed",
        },
        artifact_hashes=[],
    )
    pii = boundary_a.enqueue_trace(
        idempotency_key="pii",
        source_trace_id="trace-pii",
        source_response_id="resp-pii",
        capability="general.reasoning",
        trace={"request": {"input": synthetic_email}},
        provenance={"actor": "gateway", "policy_version": "v1"},
        policy={
            "consent": "explicit",
            "license": "permitted",
            "retention_class": "training-approved",
        },
        quality={
            "response_status": "completed",
            "quality_verdict": "passed",
            "verifier_verdict": "passed",
        },
        artifact_hashes=[],
    )
    negative = boundary_a.enqueue_trace(
        idempotency_key="license-negative",
        source_trace_id="trace-negative",
        source_response_id="resp-negative",
        capability="general.reasoning",
        trace={"request": {"input": "licensed source"}},
        provenance={"actor": "gateway", "policy_version": "v1"},
        policy={
            "consent": "explicit",
            "license": "negative",
            "retention_class": "training-approved",
        },
        quality={
            "response_status": "completed",
            "quality_verdict": "passed",
            "verifier_verdict": "passed",
        },
        artifact_hashes=[],
    )
    assert secret_record["rejection_code"] == "learning_secret_detected"
    assert pii["rejection_code"] == "learning_pii_detected"
    assert negative["rejection_code"] == "learning_license_not_permitted"
    assert boundary_a.process_pending(worker_id="dataset-builder", limit=10)["processed_count"] == 0
    assert len(boundary_a.list_candidates()) == 1

    with sqlite3.connect(boundary_a.db_path) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'formulalm_%'"
            )
        ]
        rows = {
            table: conn.execute(f"SELECT * FROM {table}").fetchall()
            for table in tables
        }
    serialized = json.dumps(rows, ensure_ascii=False)
    assert synthetic_secret not in serialized
    assert synthetic_email not in serialized


def test_registry_requires_independent_eval_canary_gates_and_explicit_rollback(tmp_path):
    _, _, app, client = make_client(tmp_path)
    response = client.post("/v1/responses", json=eligible_request())
    assert response.status_code == 201
    candidate = client.post(
        "/v1/learning/queue/process",
        json={"worker_id": "formulalm-worker", "limit": 1},
    ).json()["candidates"][0]

    dataset_response = client.post("/v1/learning/datasets", json={
        "idempotency_key": "dataset-1",
        "candidate_ids": [candidate["candidate_id"]],
        "capability": "general.reasoning",
        "builder_id": "dataset-builder",
    })
    assert dataset_response.status_code == 201
    dataset = dataset_response.json()
    assert dataset["content_sha256"].startswith("sha256:")
    assert dataset["training_started"] is False

    registry_response = client.post("/v1/learning/registry", json={
        "idempotency_key": "registry-1",
        "dataset_id": dataset["dataset_id"],
        "model_artifact_sha256": DIGEST_B,
        "training_run_id": "external-train-run-1",
        "training_actor_id": "trainer-a",
        "external_fallback": "provider-fallback",
    })
    assert registry_response.status_code == 201
    registry = registry_response.json()
    registry_id = registry["registry_id"]
    assert registry["stage"] == "shadow"
    assert registry["training_performed_by_learning_plane"] is False
    assert registry["training_execution_claimed"] is False
    assert registry["runtime_traffic_mutated"] is False
    assert registry["production_weight_mutation"] is False

    not_independent = client.post(
        f"/v1/learning/registry/{registry_id}/evaluations",
        json={
            "idempotency_key": "eval-not-independent",
            "evaluator_id": "trainer-a",
            "independent_of_training_actor": True,
            "verdict": "passed",
            "eval_suite_sha256": DIGEST_A,
            "report_sha256": DIGEST_C,
            "metrics": {"truth_score": 0.99},
        },
    )
    assert not_independent.status_code == 422
    assert not_independent.json()["detail"] == "learning_evaluator_not_independent"

    failed_eval = client.post(
        f"/v1/learning/registry/{registry_id}/evaluations",
        json={
            "idempotency_key": "eval-failed",
            "evaluator_id": "eval-council-a",
            "independent_of_training_actor": True,
            "verdict": "failed",
            "eval_suite_sha256": DIGEST_A,
            "report_sha256": DIGEST_B,
            "metrics": {"truth_score": 0.4},
        },
    )
    assert failed_eval.status_code == 201
    rejected_canary = client.post(
        f"/v1/learning/registry/{registry_id}/transitions",
        json={
            "idempotency_key": "canary-failed-eval",
            "to_stage": "canary-1",
            "evidence": {
                "evaluation_id": failed_eval.json()["evaluation_id"],
                "canary_manifest_sha256": DIGEST_C,
                "external_fallback_retained": True,
            },
        },
    )
    assert rejected_canary.status_code == 422
    assert rejected_canary.json()["detail"] == "learning_independent_eval_not_passed"

    passed_eval = client.post(
        f"/v1/learning/registry/{registry_id}/evaluations",
        json={
            "idempotency_key": "eval-passed",
            "evaluator_id": "eval-council-b",
            "independent_of_training_actor": True,
            "verdict": "passed",
            "eval_suite_sha256": DIGEST_A,
            "report_sha256": DIGEST_C,
            "metrics": {"truth_score": 0.99, "safety_score": 1.0},
        },
    )
    assert passed_eval.status_code == 201
    evaluation = passed_eval.json()
    assert evaluation["independent_of_training_actor"] is True
    assert evaluation["content_sha256"].startswith("sha256:")
    assert evaluation["auto_promote"] is False

    direct_production = client.post(
        f"/v1/learning/registry/{registry_id}/transitions",
        json={
            "idempotency_key": "direct-production",
            "to_stage": "production",
            "evidence": {},
        },
    )
    assert direct_production.status_code == 409

    transitions = [
        ("canary-1", {
            "evaluation_id": evaluation["evaluation_id"],
            "canary_manifest_sha256": DIGEST_A,
            "external_fallback_retained": True,
        }),
        ("canary-10", {
            "canary_report_sha256": DIGEST_B,
            "canary_verdict": "passed",
            "external_fallback_retained": True,
        }),
        ("canary-50", {
            "canary_report_sha256": DIGEST_C,
            "canary_verdict": "passed",
            "external_fallback_retained": True,
        }),
        ("production", {
            "canary_report_sha256": DIGEST_A,
            "release_manifest_sha256": DIGEST_B,
            "canary_verdict": "passed",
            "external_fallback_retained": True,
            "owner_approval_id": "owner-approval-1",
        }),
    ]
    for index, (stage, evidence) in enumerate(transitions):
        payload = {
            "idempotency_key": f"registry-transition-{index}",
            "to_stage": stage,
            "evidence": evidence,
        }
        result = client.post(
            f"/v1/learning/registry/{registry_id}/transitions", json=payload
        )
        assert result.status_code == 200
        assert result.json()["stage"] == stage
        assert result.json()["runtime_traffic_mutated"] is False
        assert result.json()["production_weight_mutation"] is False
        assert result.json()["auto_promote"] is False
        retry = client.post(
            f"/v1/learning/registry/{registry_id}/transitions", json=payload
        )
        assert retry.status_code == 200
        assert retry.json()["stage"] == stage

    missing_rollback_report = client.post(
        f"/v1/learning/registry/{registry_id}/transitions",
        json={
            "idempotency_key": "rollback-missing-report",
            "to_stage": "rolled-back",
            "reason": "regression",
            "evidence": {
                "rollback_target": "provider-fallback",
                "external_fallback_retained": True,
            },
        },
    )
    assert missing_rollback_report.status_code == 422

    rollback = client.post(
        f"/v1/learning/registry/{registry_id}/transitions",
        json={
            "idempotency_key": "rollback-1",
            "to_stage": "rolled-back",
            "reason": "independent canary regression",
            "evidence": {
                "rollback_target": "provider-fallback",
                "rollback_report_sha256": DIGEST_C,
                "external_fallback_retained": True,
            },
        },
    )
    assert rollback.status_code == 200
    assert rollback.json()["stage"] == "rolled-back"
    assert rollback.json()["authorized_traffic_percent"] == 0
    assert rollback.json()["runtime_traffic_mutated"] is False

    events = client.get(
        f"/v1/learning/registry/{registry_id}/transitions"
    ).json()["data"]
    assert [event["to_stage"] for event in events] == [
        "canary-1", "canary-10", "canary-50", "production", "rolled-back",
    ]
    status = client.get("/v1/learning/status").json()
    assert status["dataset_count"] == 1
    assert status["evaluations_by_verdict"] == {"failed": 1, "passed": 1}
    assert status["registry_by_stage"] == {"rolled-back": 1}
    assert status["production_weight_mutation"] is False
    assert status["runtime_traffic_mutation"] is False

    anonymous = TestClient(app)
    assert anonymous.get("/v1/learning/datasets").status_code == 401
    assert anonymous.get("/v1/learning/registry").status_code == 401

    contract = json.loads(
        (ROOT / "contracts" / "kolibri-os-v1" / "openapi.json").read_text(encoding="utf-8")
    )
    assert {
        "/v1/learning/datasets",
        "/v1/learning/datasets/{dataset_id}",
        "/v1/learning/registry",
        "/v1/learning/registry/{registry_id}",
        "/v1/learning/registry/{registry_id}/evaluations",
        "/v1/learning/registry/{registry_id}/transitions",
    }.issubset(contract["paths"])
