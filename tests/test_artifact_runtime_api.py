import importlib.util
import json
import socket
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def load_execution_api():
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    module_name = "execution_api_artifact_runtime_contract"
    spec = importlib.util.spec_from_file_location(module_name, BACKEND / "execution_api.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def make_client(tmp_path):
    execution = load_execution_api()
    db_path = tmp_path / "execution.db"
    execution.configure_execution_store(db_path)
    execution.configure_execution_auth(["test-execution-key"])
    app = FastAPI()
    app.include_router(execution.router)
    return execution, TestClient(
        app, headers={"Authorization": "Bearer test-execution-key"},
    ), db_path


def create_project(client, suffix="one"):
    response = client.post(
        "/v1/projects",
        json={"idempotency_key": f"project-{suffix}", "name": f"Project {suffix}"},
    )
    assert response.status_code == 201
    return response.json()


def create_file_artifact(client, project_id, suffix="one"):
    response = client.post(
        "/v1/artifacts",
        json={
            "idempotency_key": f"artifact-{suffix}",
            "project_id": project_id,
            "kind": "file",
            "payload": {
                "name": f"source-{suffix}.txt",
                "media_type": "text/plain",
                "uri": f"artifact://sha256/{suffix}",
                "sha256": "a" * 64,
                "size_bytes": 12,
            },
        },
    )
    assert response.status_code == 201
    return response.json()


def estimate_payload(project_id, key="estimate-one"):
    return {
        "idempotency_key": key,
        "project_id": project_id,
        "title": "Детерминированная смета",
        "currency": "RUB",
        "minor_unit": 2,
        "lines": [
            {
                "id": "line-one",
                "description": "Работа",
                "category": "labor",
                "unit": "ч",
                "quantity": "1.005",
                "unit_price_minor": 100,
                "provenance": {"source": "manual", "source_ref": "owner-input"},
            },
            {
                "id": "line-two",
                "description": "Материал",
                "category": "material",
                "unit": "шт",
                "quantity": "2.5",
                "unit_price_minor": 333,
                "provenance": {"source": "catalog", "source_ref": "catalog-2026-07"},
            },
        ],
        "overhead_rate_bps": 725,
        "tax_rate_bps": 2000,
    }


def test_canvas_has_typed_immutable_artifact_links_and_validated_graph(tmp_path):
    _, client, _ = make_client(tmp_path)
    project = create_project(client)
    artifact = create_file_artifact(client, project["id"])
    payload = {
        "idempotency_key": "canvas-one",
        "project_id": project["id"],
        "title": "Workbench",
        "nodes": [
            {
                "id": "node-source",
                "renderer": "code",
                "artifact_id": artifact["id"],
                "artifact_kind": "file",
                "position": {"x": 10, "y": 20},
            }
        ],
        "edges": [],
    }
    dry_run = client.post("/v1/canvases/validate", json=payload)
    assert dry_run.status_code == 200
    assert dry_run.json()["executed"] is False

    created = client.post("/v1/canvases", json=payload)
    duplicate = client.post("/v1/canvases", json=payload)
    assert created.status_code == duplicate.status_code == 201
    canvas = created.json()
    assert duplicate.json()["id"] == canvas["id"]
    assert canvas["schema_version"] == "kolibri.canvas.v1"
    assert canvas["status"] == "active"
    assert canvas["artifact_links"] == [
        {
            "schema_version": "kolibri.artifact-link.v1",
            "artifact_id": artifact["id"],
            "relation": "canvas-node",
            "kind": "file",
            "media_type": "text/plain",
            "state": "registered",
            "immutable_reference": True,
        }
    ]
    assert client.get(f"/v1/canvases/{canvas['id']}").json()["id"] == canvas["id"]
    assert client.get(f"/v1/canvases/{canvas['id']}/status").json()["status"] == "active"
    assert client.get(f"/v1/canvases?project_id={project['id']}").json()["data"][0]["id"] == canvas["id"]

    bad_edge = {**payload, "idempotency_key": "canvas-bad-edge", "edges": [
        {"id": "edge-one", "source": "node-source", "target": "missing-node"}
    ]}
    assert client.post("/v1/canvases", json=bad_edge).status_code == 422
    wrong_kind = json.loads(json.dumps(payload))
    wrong_kind["idempotency_key"] = "canvas-wrong-kind"
    wrong_kind["nodes"][0]["artifact_kind"] = "preview"
    assert client.post("/v1/canvases", json=wrong_kind).status_code == 409


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "http://localhost/admin",
        "http://service.internal/",
        "http://127.0.0.1/",
        "http://127.0.0.1./",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://10.20.30.40/",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
        "http://2130706433/",
        "http://0177.0.0.1/",
        "https://user:password@example.com/",
        "https://single-label-host/",
    ],
)
def test_preview_and_browser_reject_ssrf_targets(tmp_path, url):
    _, client, _ = make_client(tmp_path)
    project = create_project(client, suffix=url.replace("/", "-")[:30])
    preview = client.post(
        "/v1/previews",
        json={"idempotency_key": "preview-ssrf", "project_id": project["id"], "entry_url": url},
    )
    browser = client.post(
        "/v1/browser-sessions",
        json={"idempotency_key": "browser-ssrf", "project_id": project["id"], "start_url": url},
    )
    assert preview.status_code == 422
    assert browser.status_code == 422


def test_public_domain_is_only_queued_with_dns_rebinding_policy_and_no_dns_call(tmp_path, monkeypatch):
    _, client, _ = make_client(tmp_path)
    project = create_project(client)

    def forbidden_dns_call(*_args, **_kwargs):
        raise AssertionError("API handler must not perform network or DNS execution")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden_dns_call)
    created = client.post(
        "/v1/browser-sessions",
        json={
            "idempotency_key": "browser-public",
            "project_id": project["id"],
            "start_url": "https://example.com/work",
            "allowed_origins": ["https://cdn.example.com"],
        },
    )
    assert created.status_code == 202
    session = created.json()
    assert session["schema_version"] == "kolibri.browser-session.v1"
    assert session["status"] == "queued"
    assert session["runtime"]["adapter_status"] == "unverified"
    assert session["runtime"]["execution_started"] is False
    validation = session["network_validation"]
    assert validation["runtime_dns_verification_required"] is True
    assert validation["primary"]["dns_verification"] == "required_at_execution"
    policy = validation["primary"]["policy"]
    assert policy["require_every_resolved_address_global"] is True
    assert policy["pin_resolution_for_navigation"] is True
    assert policy["revalidate_before_each_redirect"] is True
    assert policy["fail_on_resolution_change"] is True


def test_preview_cancel_is_idempotent_and_commits_event_and_outbox_atomically(tmp_path):
    execution, client, db_path = make_client(tmp_path)
    project = create_project(client)
    payload = {
        "idempotency_key": "preview-one",
        "project_id": project["id"],
        "entry_url": "https://example.com/preview",
    }
    first = client.post("/v1/previews", json=payload)
    second = client.post("/v1/previews", json=payload)
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["schema_version"] == "kolibri.preview.v1"
    preview_id = first.json()["id"]

    cancel = {"idempotency_key": "preview-cancel-one", "reason": "owner stopped preview"}
    cancelled = client.post(f"/v1/previews/{preview_id}/cancel", json=cancel)
    retried = client.post(f"/v1/previews/{preview_id}/cancel", json=cancel)
    assert cancelled.status_code == retried.status_code == 200
    assert cancelled.json()["status"] == retried.json()["status"] == "cancelled"
    conflict = client.post(
        f"/v1/previews/{preview_id}/cancel",
        json={**cancel, "reason": "different intent"},
    )
    assert conflict.status_code == 409

    with sqlite3.connect(db_path) as conn:
        event_rows = conn.execute(
            "SELECT event_type FROM execution_events WHERE aggregate_id = ? ORDER BY sequence",
            (preview_id,),
        ).fetchall()
        outbox_rows = conn.execute(
            """SELECT status FROM execution_outbox
               WHERE event_id IN (SELECT event_id FROM execution_events WHERE aggregate_id = ?)
               ORDER BY created_at""",
            (preview_id,),
        ).fetchall()
    assert event_rows == [("preview.created",), ("preview.cancelled",)]
    assert outbox_rows == [("pending",), ("pending",)]

    execution.configure_execution_store(db_path)
    assert client.get(f"/v1/previews/{preview_id}").json()["status"] == "cancelled"


def test_estimate_money_is_decimal_minor_unit_deterministic_and_not_llm_authored(tmp_path):
    _, client, _ = make_client(tmp_path)
    project = create_project(client)
    payload = estimate_payload(project["id"])
    created = client.post("/v1/estimates", json=payload)
    duplicate = client.post("/v1/estimates", json=payload)
    assert created.status_code == duplicate.status_code == 202
    estimate = created.json()
    assert duplicate.json()["id"] == estimate["id"]
    assert estimate["schema_version"] == "kolibri.estimate.v1"
    assert estimate["status"] == "calculated"
    calculation = estimate["calculation"]
    assert calculation["engine"] == "kolibri.decimal-minor-unit.v1"
    assert calculation["rounding"] == "ROUND_HALF_UP"
    assert calculation["lines"][0]["line_total_minor"] == 101
    assert calculation["lines"][1]["line_total_minor"] == 833
    assert calculation["totals"] == {
        "categories_minor": {"labor": 101, "material": 833},
        "subtotal_minor": 934,
        "overhead_minor": 68,
        "taxable_minor": 1002,
        "tax_minor": 200,
        "grand_total_minor": 1202,
    }
    assert calculation["money_authority"] == "deterministic_calculator"
    assert calculation["llm_calculates_money"] is False
    assert len(calculation["calculation_sha256"]) == 64

    validation_payload = {key: value for key, value in payload.items() if key not in {"idempotency_key", "project_id"}}
    validation = client.post("/v1/estimates/validate", json=validation_payload)
    assert validation.status_code == 200
    assert validation.json()["calculation"]["calculation_sha256"] == calculation["calculation_sha256"]
    forbidden_total = {**payload, "idempotency_key": "estimate-forged", "grand_total_minor": 1}
    assert client.post("/v1/estimates", json=forbidden_total).status_code == 422
    changed = {**payload, "title": "Changed"}
    assert client.post("/v1/estimates", json=changed).status_code == 409


def test_document_and_build_are_queued_without_fake_adapter_success(tmp_path):
    _, client, _ = make_client(tmp_path)
    project = create_project(client)
    artifact = create_file_artifact(client, project["id"])
    estimate = client.post("/v1/estimates", json=estimate_payload(project["id"])).json()

    document = client.post(
        "/v1/documents",
        json={
            "idempotency_key": "document-one",
            "project_id": project["id"],
            "title": "Смета PDF",
            "document_type": "estimate",
            "format": "pdf-x",
            "estimate_id": estimate["id"],
        },
    )
    assert document.status_code == 202
    document_payload = document.json()
    assert document_payload["schema_version"] == "kolibri.document.v1"
    assert document_payload["status"] == "queued"
    assert document_payload["runtime"]["adapter_status"] == "unverified"
    assert document_payload["runtime"]["execution_started"] is False
    assert document_payload["estimate_snapshot"]["totals"]["grand_total_minor"] == 1202

    build_payload = {
        "idempotency_key": "build-one",
        "project_id": project["id"],
        "name": "Kolibri web build",
        "target": "web",
        "source_artifact": {
            "artifact_id": artifact["id"],
            "relation": "source",
            "expected_kind": "file",
        },
    }
    build = client.post("/v1/builds", json=build_payload)
    assert build.status_code == 202
    assert build.json()["schema_version"] == "kolibri.build.v1"
    assert build.json()["status"] == "queued"
    assert build.json()["runtime"]["adapter_status"] == "unverified"
    assert build.json()["runtime"]["arbitrary_command_allowed"] is False
    assert client.get(f"/v1/builds/{build.json()['id']}/status").json()["status"] == "queued"

    arbitrary_shell = {**build_payload, "idempotency_key": "build-shell", "command": "rm -rf /"}
    assert client.post("/v1/builds", json=arbitrary_shell).status_code == 422
    cancelled = client.post(
        f"/v1/builds/{build.json()['id']}/cancel",
        json={"idempotency_key": "build-cancel", "reason": "cancel test"},
    )
    assert cancelled.json()["status"] == "cancelled"


def test_document_content_is_sanitized_before_sqlite_persistence(tmp_path):
    _, client, db_path = make_client(tmp_path)
    project = create_project(client)
    raw_secret = "sk-secret-material-1234567890"
    response = client.post(
        "/v1/documents",
        json={
            "idempotency_key": "document-secret",
            "project_id": project["id"],
            "title": "Safe document",
            "document_type": "report",
            "format": "docx",
            "content": {"api_key": raw_secret, "body": f"redact {raw_secret}"},
        },
    )
    assert response.status_code == 202
    serialized = json.dumps(response.json())
    assert raw_secret not in serialized
    assert response.json()["sanitization_report"]["redacted_fields"] == 1
    with sqlite3.connect(db_path) as conn:
        stored = "\n".join(row[0] for row in conn.execute(
            "SELECT payload FROM execution_records UNION ALL SELECT payload FROM execution_events UNION ALL SELECT payload FROM execution_outbox"
        ))
    assert raw_secret not in stored


def test_automation_dry_run_validates_dag_retry_approval_and_never_executes(tmp_path):
    _, client, db_path = make_client(tmp_path)
    project = create_project(client)
    payload = {
        "project_id": project["id"],
        "name": "Publish verified document",
        "enabled": True,
        "trigger": {"kind": "manual", "config": {}},
        "steps": [
            {
                "id": "step-read",
                "kind": "api",
                "config": {"url": "https://example.com/data", "method": "GET"},
                "retry_policy": {"max_attempts": 2, "backoff_seconds": "1", "max_backoff_seconds": "5"},
            },
            {
                "id": "step-write",
                "kind": "document",
                "config": {"format": "pdf"},
                "depends_on": ["step-read"],
                "retry_policy": {"max_attempts": 3, "backoff_seconds": "2", "max_backoff_seconds": "10"},
                "approval": "owner",
            },
        ],
        "approval_policy": "per-side-effect",
    }
    before = sqlite3.connect(db_path).execute(
        "SELECT COUNT(*) FROM execution_records WHERE record_type = 'automation'"
    ).fetchone()[0]
    validation = client.post("/v1/automations/validate", json=payload)
    after = sqlite3.connect(db_path).execute(
        "SELECT COUNT(*) FROM execution_records WHERE record_type = 'automation'"
    ).fetchone()[0]
    assert validation.status_code == 200
    compiled = validation.json()
    assert compiled["dry_run"] is True
    assert compiled["executed"] is False
    assert compiled["topological_order"] == ["step-read", "step-write"]
    assert compiled["side_effect_step_ids"] == ["step-write"]
    assert compiled["approval_gate_count"] == 1
    assert before == after == 0

    created = client.post("/v1/automations", json={**payload, "idempotency_key": "automation-one"})
    assert created.status_code == 201
    automation = created.json()
    assert automation["schema_version"] == "kolibri.automation.v1"
    assert automation["version"] == 1
    assert automation["version_history"] == [{
        "version": 1,
        "definition_sha256": automation["definition_sha256"],
    }]
    assert automation["status"] == "degraded"
    assert automation["runtime"]["scheduler_adapter_status"] == "unverified"
    assert automation["runtime"]["execution_started"] is False
    assert automation["steps"][1]["retry_policy"]["max_attempts"] == 3

    no_approval = {**payload, "approval_policy": "none"}
    assert client.post("/v1/automations/validate", json=no_approval).status_code == 422
    cyclic = json.loads(json.dumps(payload))
    cyclic["steps"][0]["depends_on"] = ["step-write"]
    assert client.post("/v1/automations/validate", json=cyclic).status_code == 422
    raw_secret = json.loads(json.dumps(payload))
    raw_secret["steps"][0]["config"]["api_key"] = "raw-secret"
    assert client.post("/v1/automations/validate", json=raw_secret).status_code == 422
    for header_name in ("X-API-Key", "xApiKey"):
        header_secret = json.loads(json.dumps(payload))
        header_secret["steps"][0]["config"]["headers"] = {header_name: "raw-secret"}
        assert client.post("/v1/automations/validate", json=header_secret).status_code == 422
    shell = json.loads(json.dumps(payload))
    shell["steps"][0]["config"]["command"] = "uname -a"
    assert client.post("/v1/automations/validate", json=shell).status_code == 422
    unsupported_method = json.loads(json.dumps(payload))
    unsupported_method["steps"][0]["config"]["method"] = "CONNECT"
    assert client.post("/v1/automations/validate", json=unsupported_method).status_code == 422
    approval_bypass = json.loads(json.dumps(payload))
    approval_bypass["steps"][1]["approval"] = "none"
    assert client.post("/v1/automations/validate", json=approval_bypass).status_code == 422


def test_cross_project_artifact_and_estimate_links_fail_closed(tmp_path):
    _, client, _ = make_client(tmp_path)
    project_one = create_project(client, "one")
    project_two = create_project(client, "two")
    artifact = create_file_artifact(client, project_one["id"])
    estimate = client.post("/v1/estimates", json=estimate_payload(project_one["id"])).json()

    preview = client.post(
        "/v1/previews",
        json={
            "idempotency_key": "cross-project-preview",
            "project_id": project_two["id"],
            "source_artifact": {"artifact_id": artifact["id"], "relation": "source"},
        },
    )
    assert preview.status_code == 409
    document = client.post(
        "/v1/documents",
        json={
            "idempotency_key": "cross-project-document",
            "project_id": project_two["id"],
            "title": "Wrong project",
            "document_type": "estimate",
            "format": "pdf",
            "estimate_id": estimate["id"],
        },
    )
    assert document.status_code == 409
