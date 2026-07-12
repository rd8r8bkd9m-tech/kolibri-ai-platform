from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from artifact_runtime import EstimateSpec, deterministic_estimate
import capability_gateway
from estimate_artifacts import (
    EstimateVersionConflict,
    configure_estimate_artifact_store,
    materialize_public_estimate_task,
)
from execution_api import configure_execution_store
from formulalm_boundary import scan_learning_payload
import public_responses_api
from public_estimate_api import router as estimate_router
from public_responses_api import router as responses_router
from providers import ProviderGatewayError
import web_search_gateway
from vertical_tasks import (
    EstimateProviderDraftError,
    EstimateVerticalTask,
    build_deterministic_estimate_fallback,
    estimate_spec_from_provider_response,
    prepare_vertical_task,
    provider_estimate_draft_json_schema,
    verified_deterministic_estimate_fallback,
)


ORIGIN = "http://testserver"


def test_server_generated_estimate_id_is_not_payment_card_pii() -> None:
    scan = scan_learning_payload({
        "estimate_id": "estimate_4242424242424242_deadbeef",
    })

    assert scan.rejected is False
    assert scan.report["pii_findings"] == 0


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _spec(*, price_minor: int = 125_000) -> EstimateSpec:
    return EstimateSpec.model_validate({
        "title": "Смета на ремонт кухни",
        "currency": "RUB",
        "minor_unit": 2,
        "region": "Москва",
        "client_name": "Тестовый заказчик",
        "object_name": "Кухня 18 м2",
        "source_summary": "Ориентировочные цены модели, требуется проверка поставщика",
        "assumptions": ["Площадь отделки стен принята по заданию."],
        "questions": ["Нужно ли включить вывоз мусора?"],
        "lines": [
            {
                "id": "labor-1",
                "section": "Подготовка",
                "description": "Демонтаж старого покрытия",
                "category": "labor",
                "unit": "м2",
                "quantity": "18",
                "unit_price_minor": price_minor,
                "provenance": {
                    "source": "assumption",
                    "source_ref": "Ориентировочная цена, требует проверки",
                },
            },
            {
                "id": "material-1",
                "section": "Отделка",
                "description": "Краска интерьерная",
                "category": "material",
                "unit": "л",
                "quantity": "12.5",
                "unit_price_minor": 89_900,
                "provenance": {
                    "source": "supplier",
                    "source_ref": "Коммерческое предложение supplier-17",
                },
            },
        ],
        "overhead_rate_bps": 700,
        "tax_rate_bps": 0,
    })


def _verified_spec(*, price_minor: int = 125_000) -> EstimateSpec:
    payload = _spec(price_minor=price_minor).model_dump(mode="json")
    payload["source_summary"] = "Проверенные исходные данные тестового нормативного расчёта"
    payload["normative_basis"] = {
        "calculation_method": "resource",
        "normative_basis_ref": "TEST-NORMATIVE-BASE-2026",
        "normative_edition": "Тестовая редакция 2026-01-01",
        "price_level_date": "2026-01-01",
        "region": "Москва",
        "index_document_refs": [],
        "tax_scope_ref": "TEST-TAX-SCOPE-2026",
        "contract_scope_ref": "TEST-CONTRACT-SCOPE-2026",
    }
    for index, line in enumerate(payload["lines"], 1):
        line["provenance"] = {
            "source": "normative" if line["category"] == "labor" else "supplier",
            "source_ref": f"TEST-PRICE-SOURCE-{index}",
            "captured_at": "2026-01-01",
            "applicable_region": "Москва",
            "price_level_date": "2026-01-01",
            "basis_ref": f"TEST-BASIS-{index}",
            "quantity_source": "project",
            "quantity_source_ref": f"TEST-PROJECT-SHEET-{index}",
        }
    return EstimateSpec.model_validate(payload)


def _provider_draft(
    *,
    price_minor: int = 125_000,
    reported_total_minor: int = 1,
    region: str = "Москва",
) -> dict:
    spec = _verified_spec(price_minor=price_minor)
    sections: dict[str, list[dict]] = {}
    for index, line in enumerate(spec.lines, 1):
        sections.setdefault(line.section, []).append({
            "id": line.id,
            "description": line.description,
            "category": line.category,
            "unit": "m2" if index == 1 else line.unit,
            "quantity": str(line.quantity),
            "unit_price_minor": line.unit_price_minor,
            "line_total_minor": reported_total_minor,
            "price_provenance": {
                "source": "normative" if line.category == "labor" else "supplier",
                "source_ref": f"TEST-PRICE-SOURCE-{index}",
                "source_url": f"https://example.invalid/prices/{index}",
                "captured_at": "2026-01-01",
                "price_level_date": "2026-01-01",
                "applicable_region": region,
                "basis_ref": f"TEST-BASIS-{index}",
                "assumptions": ["Тестовый источник требует независимой проверки."],
            },
            "quantity_provenance": {
                "source": "project",
                "source_ref": f"TEST-PROJECT-SHEET-{index}",
                "source_url": f"https://example.invalid/project/{index}",
                "assumptions": [],
            },
            "assumptions": [],
        })
    basis = spec.normative_basis.model_dump(mode="json", exclude={"validation_status"})
    basis["region"] = region
    basis["source_urls"] = ["https://example.invalid/normative-basis"]
    basis["input_document_refs"] = ["TEST-PROJECT-SET-2026"]
    return {
        "schema_version": "kolibri.estimate-provider-draft.v1",
        "title": spec.title,
        "currency": spec.currency,
        "minor_unit": spec.minor_unit,
        "region": region,
        "client_name": spec.client_name,
        "object_name": spec.object_name,
        "object_address": spec.object_address,
        "source_summary": "Provider draft with source assertions; independent review pending",
        "normative_basis": basis,
        "sections": [
            {"id": f"section-{index}", "name": name, "lines": lines}
            for index, (name, lines) in enumerate(sections.items(), 1)
        ],
        "overhead_rate_bps": spec.overhead_rate_bps,
        "tax_rate_bps": spec.tax_rate_bps,
        "assumptions": list(spec.assumptions),
        "questions": list(spec.questions),
        "totals": {"grand_total_minor": reported_total_minor},
        "grand_total_minor": reported_total_minor,
    }


def _source_quote(price_minor: int, item: str, unit: str) -> str:
    rubles = f"{price_minor // 100:,}".replace(",", " ")
    kopecks = price_minor % 100
    amount = f"{rubles},{kopecks:02d}" if kopecks else rubles
    return f"{item}: текущая цена {amount} руб. за {unit}."


def _make_current_price_draft(draft: dict) -> dict:
    current = json.loads(json.dumps(draft, ensure_ascii=False))
    current["normative_basis"]["normative_edition"] = "Коммерческий срез 2026-07-11"
    current["normative_basis"]["price_level_date"] = "2026-07-11"
    source_urls: list[str] = []
    for section in current["sections"]:
        for line in section["lines"]:
            price = int(line["unit_price_minor"])
            provenance = line["price_provenance"]
            provenance.update({
                "captured_at": "2026-07-11",
                "price_level_date": "2026-07-11",
                "price_min_minor": price,
                "price_max_minor": price,
                "source_quote": _source_quote(price, line["description"], line["unit"]),
                "source_item": line["description"],
                "source_category": line["category"],
                "source_unit": line["unit"],
                "source_spec": None,
            })
            source_urls.append(provenance["source_url"])
    current["normative_basis"]["source_urls"] = source_urls
    return current


class _EstimatePriceCapabilityGateway:
    def validate_requested_tools(self, _tools):
        return [{
            "id": "tool:web_search", "kind": "tool", "name": "web_search",
            "status": "available", "source": {"type": "test"},
            "_aliases": ("web_search",), "_providers": ("gateway",),
        }]


class _EstimatePriceWebGateway:
    def __init__(self, draft: dict):
        self.draft = draft
        self.calls = 0

    def execute(self, query, **_kwargs):
        self.calls += 1
        citations = []
        for section in self.draft["sections"]:
            for line in section["lines"]:
                provenance = line["price_provenance"]
                quote = provenance["source_quote"]
                url = provenance["source_url"]
                citations.append({
                    "id": f"cite_{len(citations) + 1}",
                    "title": provenance["source_ref"],
                    "snippet": quote,
                    "url": url,
                    "source_host": "example.invalid",
                    "provider": "test-search",
                    "retrieved_at": "2026-07-11T00:00:00+00:00",
                    "content_sha256": _sha(json.dumps({
                        "title": provenance["source_ref"], "snippet": quote, "url": url,
                    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
                })
        return {
            "provider_context": "test price evidence",
            "tool_call": {
                "call_id": f"search_{self.calls}", "capability_id": "tool:web_search",
                "tool": "web_search", "status": "succeeded",
            },
            "evidence": {"type": "tool_execution", "output_sha256": "f" * 64},
            "citations": citations,
            "attempts": [{"provider": "test-search", "status": "succeeded"}],
            "formulalm_tap": {"tool_id": "tool:web_search", "candidate_only": True},
        }


def _configure_current_price_search(monkeypatch, draft: dict) -> None:
    monkeypatch.setattr(capability_gateway, "_gateway", _EstimatePriceCapabilityGateway())
    monkeypatch.setattr(web_search_gateway, "_gateway", _EstimatePriceWebGateway(draft))


def _verified_provider_result(text: str, *, binding: str = "f") -> dict:
    response_sha = _sha(text)
    return {
        "response": text,
        "model": "kolibri",
        "technical": {"provider_routing": {
            "selected_provider": "factory",
            "attempts": [{"attempt": 1, "provider": "factory", "status": "succeeded"}],
            "fallback_used": False,
            "artifact_refs": [],
            "evidence": [
                {
                    "type": "provider_execution",
                    "exit_code": 0,
                    "output_sha256": response_sha,
                    "output_bytes": len(text.encode("utf-8")),
                },
                {
                    "type": "deterministic_verifier",
                    "verdict": "passed",
                    "binding_sha256": binding * 64,
                },
            ],
        }},
    }


def _session_store(tmp_path):
    public_responses_api.configure_public_response_origins([ORIGIN])
    return public_responses_api.configure_public_response_store(tmp_path / "kolibri.db")


def _session(store, suffix: str):
    session, token = store.issue(ORIGIN, ttl_seconds=900)
    session["project_id"] = session["project_id"]
    return session, token


def _task(spec: EstimateSpec, *, requested=None):
    return {
        "schema_version": "kolibri.public-task.v1",
        "intent": "estimate",
        "status": "incomplete",
        "execution": {
            "status": "completed",
            "model": "kolibri",
            "provider_verified": True,
            "output_sha256": "a" * 64,
            "verifier_binding_sha256": "b" * 64,
        },
        "result": {
            "type": "deterministic_estimate",
            "estimate": spec.model_dump(mode="json"),
            "calculation": deterministic_estimate(spec),
        },
        "artifacts": [],
        "artifact_delivery": {
            "required": True,
            "status": "not_materialized",
            "requested": requested or ["pdf"],
            "delivered": [],
            "missing": requested or ["pdf"],
            "count": 0,
        },
    }


def test_model_proposal_is_normalized_and_model_totals_are_ignored():
    draft = _provider_draft(price_minor=12_500, reported_total_minor=999_999_999)
    draft["overhead_rate_bps"] = 0
    draft["sections"][0]["lines"][0]["quantity"] = "2"
    provider_json = json.dumps(draft, ensure_ascii=False)
    spec = estimate_spec_from_provider_response(provider_json)
    assert spec.lines[0].provenance.source == "normative"
    assert spec.lines[0].provenance.source_url == "https://example.invalid/prices/1"
    assert spec.lines[0].provenance.validation_status == "unverified"
    assert spec.lines[0].unit == "м²"
    calculation = deterministic_estimate(spec)
    assert calculation["lines"][0]["line_total_minor"] == 25_000
    assert calculation["totals"]["grand_total_minor"] != 999_999_999
    assert calculation["money_authority"] == "deterministic_calculator"
    assert calculation["llm_calculates_money"] is False


def test_unsourced_or_noncanonical_provider_draft_is_rejected():
    provider_json = json.dumps({
        "title": "Смета Codex",
        "currency": "RUB",
        # Codex used the currency multiplier instead of decimal-place count.
        "minor_unit": 100,
        "region": "Москва",
        "source_summary": "Ориентировочный расчёт",
        "lines": [
            {
                "id": "work-1",
                "section": "Работы",
                "description": "Монтаж",
                "category": "work",
                "unit": "м2",
                "quantity": 2,
                "unit_price_minor": 125_000,
                "provenance": "assumption",
            },
            {
                "id": "delivery-1",
                "section": "Логистика",
                "description": "Доставка",
                "category": "delivery",
                "unit": "рейс",
                "quantity": 1,
                "unit_price_minor": 50_000,
                "provenance": "assumption",
            },
        ],
        "overhead_rate_bps": 0,
        "tax_rate_bps": 0,
        "assumptions": [],
        "questions": [],
    }, ensure_ascii=False)

    with pytest.raises(ValueError):
        estimate_spec_from_provider_response(provider_json)

    invalid_source = _provider_draft()
    invalid_source["sections"][0]["lines"][0]["price_provenance"]["captured_at"] = "2026-99-99"
    with pytest.raises(ValueError):
        estimate_spec_from_provider_response(json.dumps(invalid_source, ensure_ascii=False))


def test_codex_fenced_proposal_with_surrounding_json_is_extracted_unambiguously():
    proposal = _provider_draft()
    response_text = (
        "Подготовлен структурированный результат.\n"
        "```json\n"
        f"{json.dumps(proposal, ensure_ascii=False)}\n"
        "```\n"
        'Проверка формата: {"status":"ok"}'
    )

    spec = estimate_spec_from_provider_response(response_text)

    assert spec.title == proposal["title"]
    assert spec.lines[0].unit_price_minor == 125_000
    assert deterministic_estimate(spec)["money_authority"] == "deterministic_calculator"


def test_multiple_distinct_estimate_json_objects_are_rejected():
    first = {**_provider_draft(), "title": "Первая"}
    second = {**_provider_draft(), "title": "Вторая"}
    response_text = "\n".join((
        json.dumps(first, ensure_ascii=False),
        json.dumps(second, ensure_ascii=False),
    ))

    with pytest.raises(ValueError, match="multiple JSON objects"):
        estimate_spec_from_provider_response(response_text)


def test_estimate_object_nested_in_json_array_is_not_promoted_to_top_level():
    response_text = json.dumps([_provider_draft()], ensure_ascii=False)

    with pytest.raises(ValueError, match="not a JSON object"):
        estimate_spec_from_provider_response(response_text)


def test_pdf_is_content_bound_versioned_and_session_isolated(tmp_path):
    session_store = _session_store(tmp_path)
    estimate_store = configure_estimate_artifact_store(
        tmp_path / "kolibri.db", tmp_path / "artifacts",
    )
    owner, owner_token = _session(session_store, "owner")
    other, other_token = _session(session_store, "other")
    spec = _spec()
    materialized = materialize_public_estimate_task(
        session=owner,
        response_id="resp-estimate-v1",
        task=_task(spec),
        request_metadata={},
    )
    assert materialized["status"] == "completed"
    assert materialized["persistence"]["state"] == "saved"
    assert materialized["persistence"]["version"] == 1
    artifact = materialized["artifacts"][0]
    assert artifact["name"] == "Смета на ремонт кухни — версия 1.pdf"
    assert artifact["media_type"] == "application/pdf"
    assert artifact["status"] == "materialized"
    assert artifact["immutable"] is True
    assert len(artifact["content_sha256"]) == 64
    assert len(artifact["evidence_binding_sha256"]) == 64

    app = FastAPI()
    app.include_router(estimate_router)
    owner_client = TestClient(app, headers={"Origin": ORIGIN})
    owner_client.cookies.set(public_responses_api.COOKIE_NAME, owner_token)
    response = owner_client.get(artifact["locator"])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["cache-control"].startswith("private, no-store")
    assert response.headers["content-disposition"].startswith("inline;")
    assert 'filename="kolibri-estimate-v1.pdf"' in response.headers["content-disposition"]
    assert "filename*=UTF-8''%D0%A1%D0%BC%D0%B5%D1%82%D0%B0" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")
    assert hashlib.sha256(response.content).hexdigest() == artifact["content_sha256"]

    other_client = TestClient(app, headers={"Origin": ORIGIN})
    other_client.cookies.set(public_responses_api.COOKIE_NAME, other_token)
    assert other_client.get(artifact["locator"]).status_code == 404

    stored_pdf = tmp_path / "artifacts" / f"{artifact['content_sha256']}.pdf"
    original_pdf = stored_pdf.read_bytes()
    stored_pdf.chmod(0o644)
    stored_pdf.write_bytes(b"tampered")
    assert owner_client.get(artifact["locator"]).status_code == 409
    stored_pdf.write_bytes(original_pdf)
    stored_pdf.chmod(0o444)

    updated_spec = _spec(price_minor=130_000)
    v2 = materialize_public_estimate_task(
        session=owner,
        response_id="resp-estimate-v2",
        task=_task(updated_spec),
        request_metadata={
            "estimate_id": materialized["persistence"]["estimate_id"],
            "estimate_base_version": 1,
        },
    )
    assert v2["persistence"]["version"] == 2
    assert v2["persistence"]["spec_sha256"] != materialized["persistence"]["spec_sha256"]
    current = estimate_store.get_estimate(owner["id"], v2["persistence"]["estimate_id"])
    assert current["version"] == 2
    assert len(estimate_store.list_versions(owner["id"], current["id"])) == 2

    with pytest.raises(EstimateVersionConflict, match="estimate_version_conflict"):
        materialize_public_estimate_task(
            session=owner,
            response_id="resp-estimate-stale",
            task=_task(updated_spec),
            request_metadata={
                "estimate_id": current["id"],
                "estimate_base_version": 1,
            },
        )


def test_xlsx_is_not_claimed_when_only_pdf_was_materialized(tmp_path):
    session_store = _session_store(tmp_path)
    configure_estimate_artifact_store(tmp_path / "kolibri.db", tmp_path / "artifacts")
    session, _ = _session(session_store, "owner")
    materialized = materialize_public_estimate_task(
        session=session,
        response_id="resp-estimate-partial",
        task=_task(_spec(), requested=["pdf", "xlsx"]),
        request_metadata={},
    )
    assert materialized["status"] == "incomplete"
    assert materialized["artifact_delivery"]["delivered"] == ["pdf"]
    assert materialized["artifact_delivery"]["missing"] == ["xlsx"]
    assert all(item["deliverable_type"] != "xlsx" for item in materialized["artifacts"])


def test_owner_review_feedback_is_sanitized_queued_and_never_mutates_weights(tmp_path):
    session_store = _session_store(tmp_path)
    estimate_store = configure_estimate_artifact_store(
        tmp_path / "kolibri.db", tmp_path / "artifacts",
    )
    configure_execution_store(tmp_path / "kolibri.db")
    owner, owner_token = _session(session_store, "owner")
    materialized = materialize_public_estimate_task(
        session=owner,
        response_id="resp-estimate-feedback",
        task=_task(_spec()),
        request_metadata={},
    )
    current = estimate_store.get_estimate(owner["id"], materialized["persistence"]["estimate_id"])
    app = FastAPI()
    app.include_router(estimate_router)
    client = TestClient(app, headers={"Origin": ORIGIN})
    client.cookies.set(public_responses_api.COOKIE_NAME, owner_token)

    accepted = client.post(
        f"/v1/public/estimates/{current['id']}/feedback",
        json={
            "action": "correct",
            "base_version": 1,
            "reason": "Исправлена позиция и повторно сохранена владельцем.",
            "corrections": {"line_id": "labor-1", "field": "quantity"},
            "idempotency_key": "estimate-feedback-correction-one",
        },
    )
    assert accepted.status_code == 200
    receipt = accepted.json()
    assert receipt["status"] == "queued"
    assert receipt["candidate_only"] is True
    assert receipt["async_queue"] is True
    assert receipt["production_weight_mutation"] is False

    rejected = client.post(
        f"/v1/public/estimates/{current['id']}/feedback",
        json={
            "action": "reject",
            "base_version": 1,
            "reason": "api_key=sk-" + "example-secret-value-123456789",
            "corrections": {},
            "idempotency_key": "estimate-feedback-secret-rejection",
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_code"] == "learning_secret_detected"
    with sqlite3.connect(tmp_path / "kolibri.db") as connection:
        rows = connection.execute(
            "SELECT status, payload FROM formulalm_intakes ORDER BY created_at",
        ).fetchall()
    assert rows[0][0] == "queued" and rows[0][1] is not None
    assert rows[1] == ("rejected", None)

    stale = client.post(
        f"/v1/public/estimates/{current['id']}/feedback",
        json={
            "action": "accept",
            "base_version": 2,
            "corrections": {},
            "idempotency_key": "estimate-feedback-stale",
        },
    )
    assert stale.status_code == 409


def test_public_responses_materializes_pdf_after_verified_estimate_proposal(tmp_path, monkeypatch):
    session_store = _session_store(tmp_path)
    configure_estimate_artifact_store(tmp_path / "kolibri.db", tmp_path / "artifacts")
    draft = _make_current_price_draft(
        _provider_draft(reported_total_minor=1, region="Республика Татарстан")
    )
    draft["title"] = "Предварительная смета: одноэтажный дом 100 м²"
    draft["object_name"] = "Одноэтажный жилой дом 100 м²"
    proposal = json.dumps(draft, ensure_ascii=False)
    _configure_current_price_search(monkeypatch, draft)

    async def executor(**_kwargs):
        response_sha = _sha(proposal)
        return {
            "response": proposal,
            "model": "kolibri",
            "technical": {"provider_routing": {
                "selected_provider": "factory",
                "attempts": [{"attempt": 1, "provider": "factory", "status": "succeeded"}],
                "fallback_used": False,
                "artifact_refs": [],
                "evidence": [
                    {
                        "type": "provider_execution",
                        "exit_code": 0,
                        "output_sha256": response_sha,
                        "output_bytes": len(proposal.encode("utf-8")),
                    },
                    {
                        "type": "deterministic_verifier",
                        "verdict": "passed",
                        "binding_sha256": "c" * 64,
                    },
                ],
            }},
        }

    public_responses_api.configure_public_response_executor(executor)
    session, token = _session(session_store, "owner")
    app = FastAPI()
    app.include_router(responses_router)
    app.include_router(estimate_router)
    client = TestClient(app, headers={"Origin": ORIGIN})
    client.cookies.set(public_responses_api.COOKIE_NAME, token)
    response = client.post("/v1/responses", json={
        "model": "kolibri",
        "input": "составь смету на строительство одноэтажного дома 100 м2 татарстан лениногорск",
        "idempotency_key": "estimate-proposal-one",
        "execution_mode": "codex",
        "task": {
            "intent": "estimate",
            "brief": "составь смету на строительство одноэтажного дома 100 м2 татарстан лениногорск",
            "requested_artifacts": ["pdf"],
        },
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == session["project_id"]
    assert payload["output_text"].startswith("Предварительная редактируемая смета")
    assert "Детерминированный итог" in payload["output_text"]
    assert "unit_price_minor" not in payload["output_text"]
    assert payload["verification"]["type"] == "deterministic_estimate_engine"
    assert payload["verification"]["estimate_status"] == "preliminary"
    task = payload["task"]
    assert task["status"] == "completed"
    assert task["result"]["status"] == "preliminary"
    assert task["result"]["verification"]["source_coverage_complete"] is True
    assert task["result"]["verification"]["independent_validation_complete"] is False
    assert task["result"]["calculation"]["money_authority"] == "deterministic_calculator"
    assert task["result"]["calculation"]["totals"]["grand_total_minor"] != 1
    assert task["result"]["estimate"]["lines"][0]["unit"] == "м²"
    assert task["persistence"]["version"] == 1
    assert task["artifact_delivery"]["delivered"] == ["pdf"]
    outcome = payload["estimate_outcome"]
    assert outcome["status"] == "preliminary"
    assert outcome["pricing"]["invented_prices"] is False
    assert outcome["editor"]["available"] is True
    assert outcome["editor"]["state"] == "saved"
    assert outcome["pdf"]["status"] == "materialized"
    assert outcome["pdf"]["artifact"]["content_sha256"] == task["artifacts"][0]["content_sha256"]
    assert client.get(task["artifacts"][0]["locator"]).status_code == 200


def test_exact_house_estimate_repairs_invalid_draft_once_within_total_budget(tmp_path, monkeypatch):
    session_store = _session_store(tmp_path)
    configure_estimate_artifact_store(tmp_path / "kolibri.db", tmp_path / "artifacts")
    private_marker = "PRIVATE-REJECTED-DRAFT-MUST-NOT-ENTER-REPAIR"
    invalid = json.dumps({
        "schema_version": "kolibri.estimate-provider-draft.v1",
        "title": private_marker,
        "currency": "RUB",
        "minor_unit": 2,
        "region": "Республика Татарстан",
        "source_summary": private_marker,
        "sections": [],
    }, ensure_ascii=False)
    repaired_draft = _make_current_price_draft(
        _provider_draft(
            price_minor=12_500,
            reported_total_minor=999_999_999,
            region="Республика Татарстан",
        )
    )
    repaired_draft["title"] = "Предварительная смета: дом 100 м², Лениногорск"
    repaired = json.dumps(repaired_draft, ensure_ascii=False)
    _configure_current_price_search(monkeypatch, repaired_draft)
    calls: list[dict] = []

    async def executor(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return _verified_provider_result(invalid, binding="a")
        assert private_marker not in json.dumps(kwargs["messages"], ensure_ascii=False)
        return _verified_provider_result(repaired, binding="b")

    public_responses_api.configure_public_response_executor(executor)
    _session_value, token = _session(session_store, "owner")
    app = FastAPI()
    app.include_router(responses_router)
    app.include_router(estimate_router)
    client = TestClient(app, headers={"Origin": ORIGIN})
    client.cookies.set(public_responses_api.COOKIE_NAME, token)
    brief = "составь смету на строительство одноэтажного дома 100 м2 татарстан лениногорск"

    started = time.monotonic()
    response = client.post("/v1/responses", json={
        "model": "kolibri",
        "input": brief,
        "idempotency_key": "estimate-repair-leninogorsk-100m2",
        "execution_mode": "codex",
        "task": {
            "intent": "estimate",
            "brief": brief,
            "requested_artifacts": ["pdf"],
        },
    })
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert elapsed < 2
    assert len(calls) == 2
    assert calls[0]["timeout_seconds"] == public_responses_api.ESTIMATE_PROVIDER_INITIAL_BUDGET_SECONDS
    assert 0 < calls[1]["timeout_seconds"] <= public_responses_api.ESTIMATE_PROVIDER_REPAIR_BUDGET_SECONDS
    assert sum(call["timeout_seconds"] for call in calls) <= 80
    assert calls[1]["response_id"].endswith("-repair")
    payload = response.json()
    task = payload["task"]
    assert task["status"] == "completed"
    assert task["result"]["type"] == "deterministic_estimate"
    assert task["result"]["status"] == "preliminary"
    assert task["result"]["calculation"]["totals"]["grand_total_minor"] != 999_999_999
    assert task["artifact_delivery"]["delivered"] == ["pdf"]
    pdf = client.get(task["artifacts"][0]["locator"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_estimate_source_decline_is_never_retried_and_returns_truthful_readiness(tmp_path):
    session_store = _session_store(tmp_path)
    configure_estimate_artifact_store(tmp_path / "kolibri.db", tmp_path / "artifacts")
    declined = json.dumps({
        "schema_version": "kolibri.estimate-provider-declined.v1",
        "reason": "sources_unavailable",
    })
    calls: list[dict] = []

    async def executor(**kwargs):
        calls.append(kwargs)
        return _verified_provider_result(declined, binding="d")

    public_responses_api.configure_public_response_executor(executor)
    _session_value, token = _session(session_store, "owner")
    app = FastAPI()
    app.include_router(responses_router)
    app.include_router(estimate_router)
    client = TestClient(app, headers={"Origin": ORIGIN})
    client.cookies.set(public_responses_api.COOKIE_NAME, token)
    brief = "составь смету на строительство одноэтажного дома 100 м2 татарстан лениногорск"

    response = client.post("/v1/responses", json={
        "model": "kolibri",
        "input": brief,
        "idempotency_key": "estimate-source-decline-no-retry",
        "task": {"intent": "estimate", "brief": brief, "requested_artifacts": ["pdf"]},
    })

    assert response.status_code == 200
    assert len(calls) == 1
    task = response.json()["task"]
    assert task["status"] == "incomplete"
    assert task["execution"]["fallback_reason"] == "estimate_sources_unavailable"
    assert task["execution"]["proposal_validation"] == {"code": "sources_unavailable"}
    assert task["result"]["readiness"]["monetary_status"] == "not_calculated"
    assert "calculation" not in task["result"]
    assert task["artifact_delivery"]["delivered"] == ["pdf"]


def test_unverified_codex_multiplier_proposal_is_gated_without_money(tmp_path):
    session_store = _session_store(tmp_path)
    configure_estimate_artifact_store(tmp_path / "kolibri.db", tmp_path / "artifacts")
    proposal = json.dumps({
        "title": "Черновая смета на отделку",
        "currency": "RUB",
        "minor_unit": 100,
        "region": "Москва",
        "source_summary": "Ориентировочные цены требуют проверки",
        "lines": [
            {
                "id": "work-1",
                "section": "Отделка",
                "description": "Подготовка стен",
                "category": "work",
                "unit": "м2",
                "quantity": 20,
                "unit_price_minor": 80_000,
                "provenance": "assumption",
            },
            {
                "id": "delivery-1",
                "section": "Логистика",
                "description": "Доставка материалов",
                "category": "delivery",
                "unit": "рейс",
                "quantity": 1,
                "unit_price_minor": 150_000,
                "provenance": "assumption",
            },
        ],
        "overhead_rate_bps": 1_000,
        "tax_rate_bps": 0,
        "assumptions": ["Цены ориентировочные"],
        "questions": [],
    }, ensure_ascii=False)

    async def executor(**_kwargs):
        response_sha = _sha(proposal)
        return {
            "response": proposal,
            "model": "kolibri",
            "technical": {"provider_routing": {
                "selected_provider": "factory",
                "attempts": [{"attempt": 1, "provider": "factory", "status": "succeeded"}],
                "fallback_used": False,
                "artifact_refs": [],
                "evidence": [
                    {
                        "type": "provider_execution",
                        "exit_code": 0,
                        "output_sha256": response_sha,
                        "output_bytes": len(proposal.encode("utf-8")),
                    },
                    {
                        "type": "deterministic_verifier",
                        "verdict": "passed",
                        "binding_sha256": "d" * 64,
                    },
                ],
            }},
        }

    public_responses_api.configure_public_response_executor(executor)
    _session_value, token = _session(session_store, "owner")
    app = FastAPI()
    app.include_router(responses_router)
    app.include_router(estimate_router)
    client = TestClient(app, headers={"Origin": ORIGIN})
    client.cookies.set(public_responses_api.COOKIE_NAME, token)

    response = client.post("/v1/responses", json={
        "model": "kolibri",
        "input": "Составь смету",
        "idempotency_key": "codex-multiplier-proposal",
        "execution_mode": "codex",
        "task": {
            "intent": "estimate",
            "brief": "Отделка стен",
            "region": "Москва",
            "requested_artifacts": ["pdf"],
        },
    })

    assert response.status_code == 200
    payload = response.json()
    task = payload["task"]
    assert task["status"] == "incomplete"
    assert task["result"]["type"] == "estimate_readiness"
    assert task["result"]["readiness"]["status"] == "needs_input"
    assert task["result"]["readiness"]["monetary_status"] == "not_calculated"
    assert "unit_price_minor" not in payload["output_text"]
    assert task["artifact_delivery"]["delivered"] == ["pdf"]
    assert "persistence" not in task
    pdf = client.get(task["artifacts"][0]["locator"])
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")


def test_provider_estimate_contract_is_bounded_to_consolidated_json():
    task = EstimateVerticalTask.model_validate({
        "intent": "estimate",
        "brief": "Составь смету на строительство одноэтажного дома 100 м2",
    })
    instructions, _ = prepare_vertical_task(task)

    assert '"max_lines":32' in instructions
    assert '"max_response_bytes":24576' in instructions
    assert "Return sections with at most 32 consolidated lines" in instructions

    proposal = _provider_draft()
    template = {
        **proposal["sections"][0]["lines"][0],
        "description": "x",
        "price_provenance": {
            "source": "catalog", "source_ref": "x", "source_url": "https://x.io/p",
            "captured_at": "2026-01-01", "price_level_date": "2026-01-01",
            "applicable_region": "Москва", "basis_ref": "x", "assumptions": [],
        },
        "quantity_provenance": {
            "source": "project", "source_ref": "x", "source_url": "https://x.io/q",
            "assumptions": [],
        },
        "assumptions": [],
    }
    proposal["sections"] = [
        {
            "id": "section-a",
            "name": "Раздел A",
            "lines": [{**template, "id": f"line-{index}"} for index in range(16)],
        },
        {
            "id": "section-b",
            "name": "Раздел B",
            "lines": [{**template, "id": f"line-{index}"} for index in range(16, 33)],
        },
    ]
    with pytest.raises(ValueError, match="exceeds 32 consolidated lines"):
        estimate_spec_from_provider_response(json.dumps(proposal, ensure_ascii=False))
    oversized = json.dumps(_provider_draft(), ensure_ascii=False) + (" " * 25_000)
    with pytest.raises(ValueError, match="exceeds 24576 UTF-8 bytes"):
        estimate_spec_from_provider_response(oversized)


def test_provider_estimate_prompt_schema_is_compact_strict_and_has_truthful_decline():
    schema = provider_estimate_draft_json_schema()
    encoded = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))

    assert len(encoded.encode("utf-8")) < 5_000
    assert "$defs" not in schema
    assert len(schema["oneOf"]) == 2
    draft, declined = schema["oneOf"]
    assert draft["additionalProperties"] is False
    assert draft["properties"]["normative_basis"]["additionalProperties"] is False
    line = draft["properties"]["sections"]["items"]["properties"]["lines"]["items"]
    assert line["additionalProperties"] is False
    assert line["properties"]["price_provenance"]["additionalProperties"] is False
    assert line["properties"]["quantity_provenance"]["additionalProperties"] is False
    assert declined == {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"const": "kolibri.estimate-provider-declined.v1"},
            "reason": {"const": "sources_unavailable"},
        },
        "required": ["schema_version", "reason"],
    }


def test_provider_estimate_validation_exposes_only_safe_classification():
    private_marker = "PRIVATE-PROVIDER-CONTENT-MUST-NOT-LEAK"
    draft = _provider_draft()
    draft["sections"][0]["lines"][0]["price_provenance"].pop("source_url")
    draft["source_summary"] = private_marker

    with pytest.raises(EstimateProviderDraftError) as raised:
        estimate_spec_from_provider_response(json.dumps(draft, ensure_ascii=False))

    classification = raised.value.classification()
    serialized = json.dumps(classification, ensure_ascii=False)
    assert classification["code"] == "price_provenance_invalid"
    assert any("price_provenance.source_url" in field for field in classification["fields"])
    assert private_marker not in serialized


def test_production_house_request_returns_bound_readiness_and_real_checklist_pdf(tmp_path):
    session_store = _session_store(tmp_path)
    configure_estimate_artifact_store(tmp_path / "kolibri.db", tmp_path / "artifacts")

    async def exhausted_executor(**_kwargs):
        raise ProviderGatewayError({
            "selected_provider": None,
            "attempts": [
                {
                    "attempt": 1,
                    "provider": "factory",
                    "provider_model": "mimo",
                    "status": "failed",
                    "error_type": "provider_timeout",
                },
                {
                    "attempt": 2,
                    "provider": "factory",
                    "provider_model": "codex",
                    "status": "failed",
                    "error_type": "provider_timeout",
                },
            ],
            "fallback_used": True,
            "evidence": [],
            "error_type": "provider_timeout",
        })

    public_responses_api.configure_public_response_executor(exhausted_executor)
    _session_value, token = _session(session_store, "owner")
    _other_session, other_token = _session(session_store, "other")
    app = FastAPI()
    app.include_router(responses_router)
    app.include_router(estimate_router)
    client = TestClient(app, headers={"Origin": ORIGIN})
    client.cookies.set(public_responses_api.COOKIE_NAME, token)

    response = client.post("/v1/responses", json={
        "model": "kolibri",
        "input": "составь смету на строительство одноэтажного дома 100 м2 татарстан лениногорск",
        "idempotency_key": "estimate-timeout-leninogorsk-100m2",
        "execution_mode": "fast",
        "task": {
            "intent": "estimate",
            "brief": "составь смету на строительство одноэтажного дома 100 м2 татарстан лениногорск",
            "requested_artifacts": ["pdf"],
        },
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["verification"]["type"] == "deterministic_estimate_readiness"
    assert payload["verification"]["provider_verified"] is False
    assert payload["verification"]["normative_verified"] is False
    assert payload["verification"]["output_sha256"] == _sha(payload["output_text"])
    task = payload["task"]
    assert task["status"] == "incomplete"
    assert task["execution"]["provider_verified"] is False
    assert task["execution"]["provider_status"] == "failed"
    assert task["execution"]["engine_verified"] is True
    assert task["execution"]["fallback_reason"] == "provider_timeout"
    assert verified_deterministic_estimate_fallback(task) is True
    assert task["result"]["type"] == "estimate_readiness"
    readiness = task["result"]["readiness"]
    assert readiness["status"] == "needs_input"
    assert readiness["monetary_status"] == "not_calculated"
    assert readiness["normative_verified"] is False
    assert readiness["known_facts"] == {
        "object_type": "one_storey_house",
        "object_type_label": "Одноэтажный жилой дом",
        "region": "Республика Татарстан",
        "locality": "Лениногорск",
        "currency": "RUB",
        "storeys": 1,
        "gross_area_m2": "100",
    }
    assert len(readiness["required_inputs"]) == 6
    assert all(item["status"] == "missing" for item in readiness["required_inputs"])
    assert len(readiness["editor"]["fields"]) > 20
    assert all(section["items"] == [] for section in readiness["draft_sections"])
    serialized_readiness = json.dumps(readiness, ensure_ascii=False).lower()
    for forbidden in (
        "unit_price_minor", "line_total_minor", "grand_total_minor",
        "subtotal_minor", '"totals"', '"calculation"',
    ):
        assert forbidden not in serialized_readiness
    proof = task["result"]["generation"]
    assert proof["readiness_sha256"] == hashlib.sha256(
        json.dumps(readiness, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert "persistence" not in task
    assert task["artifact_delivery"]["delivered"] == ["pdf"]
    assert task["artifact_delivery"]["missing"] == []
    outcome = payload["estimate_outcome"]
    assert outcome["status"] == "needs_input"
    assert outcome["pricing"] == {
        "status": "not_calculated",
        "invented_prices": False,
    }
    assert outcome["editor"]["available"] is True
    assert outcome["editor"]["mode"] == "input_requirements"
    assert outcome["pdf"]["status"] == "materialized"
    assert "Денежный итог не рассчитан" in payload["output_text"]
    assert "PDF-чеклист сформирован" in payload["output_text"]
    artifact = task["artifacts"][0]
    assert outcome["pdf"]["artifact"]["content_sha256"] == artifact["content_sha256"]
    assert artifact["document_role"] == "estimate_input_checklist"
    assert artifact["readiness_sha256"] == proof["readiness_sha256"]
    assert artifact["task_binding_sha256"] == proof["binding_sha256"]
    pdf = client.get(artifact["locator"])
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    assert hashlib.sha256(pdf.content).hexdigest() == artifact["content_sha256"]
    assert pdf.headers["x-content-sha256"] == artifact["content_sha256"]
    assert pdf.headers["x-kolibri-artifact-binding"] == artifact["evidence_binding_sha256"]
    stored_pdf = tmp_path / "artifacts" / f"{artifact['content_sha256']}.pdf"
    original_pdf = stored_pdf.read_bytes()
    stored_pdf.chmod(0o644)
    stored_pdf.write_bytes(b"tampered readiness checklist")
    assert client.get(artifact["locator"]).status_code == 409
    stored_pdf.write_bytes(original_pdf)
    stored_pdf.chmod(0o444)
    other_client = TestClient(app, headers={"Origin": ORIGIN})
    other_client.cookies.set(public_responses_api.COOKIE_NAME, other_token)
    assert other_client.get(artifact["locator"]).status_code == 404


def test_provider_reviewed_house_proposal_is_replaced_by_non_monetary_readiness(tmp_path):
    session_store = _session_store(tmp_path)
    configure_estimate_artifact_store(tmp_path / "kolibri.db", tmp_path / "artifacts")
    proposal = json.dumps({
        "schema_version": "kolibri.estimate-proposal.v1",
        **_spec().model_dump(mode="json"),
    }, ensure_ascii=False)

    async def executor(**_kwargs):
        response_sha = _sha(proposal)
        return {
            "response": proposal,
            "model": "kolibri",
            "technical": {"provider_routing": {
                "selected_provider": "factory",
                "attempts": [{"attempt": 1, "provider": "factory", "status": "succeeded"}],
                "fallback_used": False,
                "artifact_refs": [],
                "evidence": [
                    {
                        "type": "provider_execution",
                        "exit_code": 0,
                        "output_sha256": response_sha,
                        "output_bytes": len(proposal.encode("utf-8")),
                    },
                    {
                        "type": "deterministic_verifier",
                        "verdict": "passed",
                        "binding_sha256": "e" * 64,
                    },
                ],
            }},
        }

    public_responses_api.configure_public_response_executor(executor)
    _session_value, token = _session(session_store, "owner")
    app = FastAPI()
    app.include_router(responses_router)
    app.include_router(estimate_router)
    client = TestClient(app, headers={"Origin": ORIGIN})
    client.cookies.set(public_responses_api.COOKIE_NAME, token)
    brief = "составь смету на строительство одноэтажного дома 100 м2 татарстан лениногорск"

    response = client.post("/v1/responses", json={
        "model": "kolibri",
        "input": brief,
        "stream": False,
        "idempotency_key": "provider-reviewed-house-readiness",
        "execution_mode": "fast",
        "task": {
            "intent": "estimate",
            "brief": brief,
            "requested_artifacts": ["pdf"],
        },
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert "unit_price_minor" not in payload["output_text"]
    assert "Денежный итог не рассчитан" in payload["output_text"]
    assert payload["verification"]["type"] == "deterministic_estimate_readiness"
    assert payload["verification"]["provider_verified"] is True
    assert payload["verification"]["provider_output_sha256"] == _sha(proposal)
    task = payload["task"]
    assert task["status"] == "incomplete"
    assert task["execution"]["provider_verified"] is True
    assert task["result"]["type"] == "estimate_readiness"
    assert task["result"]["generation"]["source_mode"] == "provider_reviewed"
    assert task["result"]["readiness"]["monetary_status"] == "not_calculated"
    assert task["artifact_delivery"]["delivered"] == ["pdf"]
    pdf = client.get(task["artifacts"][0]["locator"])
    assert pdf.status_code == 200
    assert hashlib.sha256(pdf.content).hexdigest() == task["artifacts"][0]["content_sha256"]


def test_readiness_gate_handles_other_briefs_and_rejects_tampered_proof(tmp_path):
    two_storey = EstimateVerticalTask.model_validate({
        "intent": "estimate",
        "brief": "Составь смету на строительство двухэтажного дома 100 м2",
        "requested_artifacts": ["pdf"],
    })
    two_storey_gate = build_deterministic_estimate_fallback(two_storey, reason="provider_timeout")
    assert two_storey_gate is not None
    assert two_storey_gate["result"]["readiness"]["status"] == "needs_input"
    assert two_storey_gate["result"]["readiness"]["known_facts"]["object_type"] == "unspecified"
    assert "calculation" not in two_storey_gate["result"]

    one_storey = EstimateVerticalTask.model_validate({
        "intent": "estimate",
        "brief": "Составь смету на строительство одноэтажного дома 100 м2",
        "requested_artifacts": ["pdf"],
    })
    fallback = build_deterministic_estimate_fallback(one_storey, reason="provider_timeout")
    assert fallback is not None
    assert fallback["result"]["generation"]["fallback_reason"] == "provider_timeout"
    assert fallback["result"]["readiness"]["known_facts"]["locality"] is None
    assert fallback["result"]["readiness"]["monetary_status"] == "not_calculated"
    unsafe_reason = build_deterministic_estimate_fallback(one_storey, reason="timeout\nsecret")
    assert unsafe_reason is not None
    assert unsafe_reason["result"]["generation"]["fallback_reason"] == "provider_unavailable"
    fallback["result"]["generation"]["input_facts"]["gross_area_m2"] = "200"
    assert verified_deterministic_estimate_fallback(fallback) is False

    session_store = _session_store(tmp_path)
    configure_estimate_artifact_store(tmp_path / "kolibri.db", tmp_path / "artifacts")
    session, _token = _session(session_store, "owner")
    unchanged = materialize_public_estimate_task(
        session=session,
        response_id="resp-tampered-local-engine",
        task=fallback,
        request_metadata={},
    )
    assert unchanged == fallback
    assert "persistence" not in unchanged
    assert unchanged["artifacts"] == []
