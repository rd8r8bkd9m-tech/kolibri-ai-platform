from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from artifact_runtime import EstimateSpec, deterministic_estimate
from estimate_artifacts import (
    EstimateVersionConflict,
    configure_estimate_artifact_store,
    materialize_public_estimate_task,
)
import public_responses_api
from public_estimate_api import router as estimate_router
from public_responses_api import router as responses_router
from vertical_tasks import (
    estimate_spec_from_provider_response,
)


ORIGIN = "http://testserver"


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
    provider_json = json.dumps({
        "schema_version": "kolibri.estimate-proposal.v1",
        "title": "Черновая смета",
        "currency": "RUB",
        "minor_unit": 2,
        "region": "Москва",
        "source_summary": "Цены модели требуют проверки",
        "lines": [{
            "id": "line-provider",
            "section": "Работы",
            "description": "Монтаж",
            "category": "labor",
            "unit": "м2",
            "quantity": "2",
            "unit_price_minor": 12_500,
            "line_total_minor": 999_999_999,
            "provenance": {"source": "catalog"},
        }],
        "totals": {"grand_total_minor": 1},
        "overhead_rate_bps": 0,
        "tax_rate_bps": 0,
        "assumptions": [],
        "questions": [],
    }, ensure_ascii=False)
    spec = estimate_spec_from_provider_response(provider_json)
    assert spec.lines[0].provenance.source == "assumption"
    assert spec.lines[0].provenance.source_ref
    calculation = deterministic_estimate(spec)
    assert calculation["lines"][0]["line_total_minor"] == 25_000
    assert calculation["totals"]["grand_total_minor"] == 25_000
    assert calculation["money_authority"] == "deterministic_calculator"
    assert calculation["llm_calculates_money"] is False


def test_codex_multiplier_minor_unit_and_string_provenance_are_normalized():
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

    spec = estimate_spec_from_provider_response(provider_json)

    assert spec.minor_unit == 2
    assert [line.category for line in spec.lines] == ["labor", "service"]
    assert all(line.provenance.source == "assumption" for line in spec.lines)
    assert deterministic_estimate(spec)["totals"]["grand_total_minor"] == 300_000


def test_codex_fenced_proposal_with_surrounding_json_is_extracted_unambiguously():
    proposal = {
        "schema_version": "kolibri.estimate-proposal.v1",
        **_spec().model_dump(mode="json"),
    }
    proposal["lines"][0]["unit_price_minor"] = " 125\u202f000 "
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
    first = {**_spec().model_dump(mode="json"), "title": "Первая"}
    second = {**_spec().model_dump(mode="json"), "title": "Вторая"}
    response_text = "\n".join((
        json.dumps(first, ensure_ascii=False),
        json.dumps(second, ensure_ascii=False),
    ))

    with pytest.raises(ValueError, match="multiple JSON objects"):
        estimate_spec_from_provider_response(response_text)


def test_estimate_object_nested_in_json_array_is_not_promoted_to_top_level():
    response_text = json.dumps([_spec().model_dump(mode="json")], ensure_ascii=False)

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


def test_public_responses_materializes_pdf_after_verified_estimate_proposal(tmp_path):
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
        "input": "Составь смету на ремонт кухни в Москве",
        "idempotency_key": "estimate-proposal-one",
        "execution_mode": "codex",
        "task": {
            "intent": "estimate",
            "brief": "Ремонт кухни 18 м2",
            "region": "Москва",
            "requested_artifacts": ["pdf"],
        },
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == session["project_id"]
    task = payload["task"]
    assert task["status"] == "completed"
    assert task["result"]["calculation"]["money_authority"] == "deterministic_calculator"
    assert task["persistence"]["version"] == 1
    assert task["artifact_delivery"]["delivered"] == ["pdf"]
    assert client.get(task["artifacts"][0]["locator"]).status_code == 200


def test_public_responses_materializes_codex_multiplier_proposal(tmp_path):
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
    task = response.json()["task"]
    assert task["status"] == "completed"
    assert task["result"]["estimate"]["minor_unit"] == 2
    assert task["artifact_delivery"]["delivered"] == ["pdf"]
    assert task["persistence"]["version"] == 1
    pdf = client.get(task["artifacts"][0]["locator"])
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
