from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import estimate_artifacts
import public_responses_api
from estimate_artifacts import configure_estimate_artifact_store, materialize_public_estimate_task
from public_estimate_api import router as estimate_router
from public_responses_api import router as responses_router
from vertical_tasks import (
    EstimateVerticalTask,
    build_vertical_result,
    estimate_product_outcome,
    prepare_vertical_task,
    verified_deterministic_estimate_result,
)


def _draft() -> dict:
    return {
        "schema_version": "kolibri.estimate-provider-draft.v2",
        "title": "Предварительная смета: одноэтажный дом 100 м², Лениногорск",
        "currency": "RUB",
        "minor_unit": 2,
        "region": "Республика Татарстан, Лениногорск",
        "client_name": None,
        "object_name": "Одноэтажный жилой дом 100 м²",
        "object_address": None,
        "source_summary": "Предварительная ресурсная оценка основной модели",
        "sections": [
            {
                "id": "foundation",
                "name": "Фундамент",
                "lines": [
                    {
                        "id": "foundation-work",
                        "description": "Устройство монолитного фундамента",
                        "category": "labor",
                        "unit": "м³",
                        "quantity": 24,
                        "unit_price_minor": 650_000,
                        # Malformed external enrichment must be discarded;
                        # it cannot suppress the primary model's useful row.
                        "price_provenance": {
                            "source": "supplier",
                            "source_ref": "Неполный внешний ответ",
                            "source_url": "not-a-public-url",
                        },
                        "assumptions": ["Тип фундамента уточнить по геологии и проекту."],
                    },
                    {
                        "id": "foundation-concrete",
                        "description": "Бетон товарный для фундамента",
                        "category": "material",
                        "unit": "м³",
                        "quantity": 24,
                        "unit_price_minor": 920_000,
                        "assumptions": ["Марку и логистику подтвердить проектом и поставщиком."],
                    },
                ],
            },
            {
                "id": "walls",
                "name": "Стены и перегородки",
                "lines": [
                    {
                        "id": "walls-work",
                        "description": "Кладка наружных стен",
                        "category": "labor",
                        "unit": "м²",
                        "quantity": 150,
                        "unit_price_minor": 210_000,
                        "assumptions": ["Площадь принята предварительно по брифу."],
                    },
                    {
                        "id": "walls-block",
                        "description": "Газобетонные блоки",
                        "category": "material",
                        "unit": "м³",
                        "quantity": 45,
                        "unit_price_minor": 780_000,
                        "assumptions": ["Плотность и толщина требуют проектного подтверждения."],
                    },
                ],
            },
        ],
        "assumptions": ["Состав и цены предварительные до рабочего проекта."],
        "questions": ["Какой тип фундамента принят проектом?"],
        "overhead_rate_bps": 700,
        "tax_rate_bps": 0,
        # Deliberately wrong provider totals: they are ignored.
        "reported_totals": {"grand_total_minor": 1},
        "grand_total_minor": 1,
    }


def _provider_result(response_text: str) -> dict:
    encoded = response_text.encode("utf-8")
    return {
        "response": response_text,
        "model": "kolibri",
        "technical": {
            "provider_routing": {
                "selected_provider": "factory",
                "attempts": [{"provider": "factory", "status": "succeeded"}],
                "artifact_refs": [],
                "evidence": [
                    {
                        "type": "provider_execution",
                        "exit_code": 0,
                        "output_sha256": hashlib.sha256(encoded).hexdigest(),
                        "output_bytes": len(encoded),
                    },
                    {
                        "type": "deterministic_verifier",
                        "verdict": "passed",
                        "binding_sha256": "b" * 64,
                    },
                ],
            },
        },
    }


def test_primary_model_draft_opens_full_editor_without_external_price_sources(tmp_path):
    request = EstimateVerticalTask.model_validate({
        "intent": "estimate",
        "brief": "Составь смету на одноэтажный дом 100 м2 в Лениногорске",
        "region": "Республика Татарстан, Лениногорск",
        "requested_artifacts": ["pdf"],
    })
    instructions, calculation = prepare_vertical_task(request)
    assert "kolibri.estimate-provider-draft.v2" in instructions
    assert "Missing external sources must never turn the response into a questionnaire-only brief" in instructions
    assert calculation is None

    response_text = json.dumps(_draft(), ensure_ascii=False)
    task = build_vertical_result(
        request,
        _provider_result(response_text),
        calculation,
        estimate_source_mode="controlled_search",
        source_evidence=[],
    )

    assert task["result"]["type"] == "deterministic_estimate"
    assert task["result"]["status"] == "preliminary"
    assert len(task["result"]["estimate"]["lines"]) == 4
    assert all(
        line["provenance"]["source"] == "assumption"
        and line["provenance"]["validation_status"] == "unverified"
        for line in task["result"]["estimate"]["lines"]
    )
    assert "Некоторые внешние данные отклонены валидатором" in " ".join(
        task["result"]["estimate"]["assumptions"],
    )
    calculation = task["result"]["calculation"]
    assert calculation["money_authority"] == "deterministic_calculator"
    assert calculation["llm_calculates_money"] is False
    assert calculation["totals"]["grand_total_minor"] != 1
    assert verified_deterministic_estimate_result(task) is True

    configure_estimate_artifact_store(tmp_path / "kolibri.db", tmp_path / "artifacts")
    materialized = materialize_public_estimate_task(
        session={
            "id": "session-estimate-v2",
            "project_id": "project_ephemeral_estimate_v2",
            "expires_at": time.time() + 900,
        },
        response_id="response-estimate-v2",
        task=task,
        request_metadata={},
    )
    assert materialized["status"] == "completed"
    assert materialized["persistence"]["state"] == "saved"
    assert materialized["artifact_delivery"]["delivered"] == ["pdf"]
    artifact = materialized["artifacts"][0]
    assert artifact["media_type"] == "application/pdf"
    assert artifact["size_bytes"] > 1_000
    outcome = estimate_product_outcome(materialized)
    assert outcome is not None
    assert outcome["status"] == "preliminary"
    assert outcome["pricing"]["source_status"] == "model_suggestion_unverified"
    assert outcome["pricing"]["model_price_suggestions"] is True
    assert outcome["editor"]["available"] is True
    assert outcome["editor"]["mode"] == "estimate"
    assert outcome["pdf"]["status"] == "materialized"


def test_public_response_returns_rows_editor_and_real_pdf_not_a_brief(tmp_path):
    previous = {
        "response_store": public_responses_api._STORE,
        "executor": public_responses_api._EXECUTOR,
        "origins": public_responses_api._PUBLIC_ORIGINS,
        "estimate_store": estimate_artifacts._STORE,
    }
    origin = "http://testserver"
    try:
        public_responses_api.configure_public_response_origins([origin])
        response_store = public_responses_api.configure_public_response_store(
            tmp_path / "public.db",
        )
        configure_estimate_artifact_store(tmp_path / "public.db", tmp_path / "artifacts")
        proposal = json.dumps(_draft(), ensure_ascii=False)

        async def executor(**_kwargs):
            return _provider_result(proposal)

        public_responses_api.configure_public_response_executor(executor)
        _session, session_cookie = response_store.issue(origin, ttl_seconds=900)
        app = FastAPI()
        app.include_router(responses_router)
        app.include_router(estimate_router)
        client = TestClient(app, headers={"Origin": origin})
        client.cookies.set(public_responses_api.COOKIE_NAME, session_cookie)
        brief = "Составь смету на одноэтажный дом 100 м2 в Татарстане, Лениногорск"
        response = client.post("/v1/responses", json={
            "model": "kolibri",
            "input": brief,
            "idempotency_key": "primary-model-estimate-v2",
            "execution_mode": "codex",
            "task": {
                "intent": "estimate",
                "brief": brief,
                "requested_artifacts": ["pdf"],
            },
        })

        assert response.status_code == 200
        payload = response.json()
        assert payload["output_text"].startswith("Предварительная редактируемая смета")
        assert "Детерминированный итог" in payload["output_text"]
        assert "Денежный итог не рассчитан" not in payload["output_text"]
        assert payload["task"]["result"]["type"] == "deterministic_estimate"
        assert len(payload["task"]["result"]["estimate"]["lines"]) == 4
        assert payload["estimate_outcome"]["editor"]["available"] is True
        assert payload["estimate_outcome"]["pricing"]["source_status"] == "model_suggestion_unverified"
        assert payload["estimate_outcome"]["pdf"]["status"] == "materialized"
        artifact = payload["estimate_outcome"]["pdf"]["artifact"]
        pdf = client.get(artifact["locator"])
        assert pdf.status_code == 200
        assert pdf.headers["content-type"].startswith("application/pdf")
        assert pdf.content.startswith(b"%PDF-")
        assert hashlib.sha256(pdf.content).hexdigest() == artifact["content_sha256"]
    finally:
        public_responses_api._STORE = previous["response_store"]
        public_responses_api._EXECUTOR = previous["executor"]
        public_responses_api._PUBLIC_ORIGINS = previous["origins"]
        estimate_artifacts._STORE = previous["estimate_store"]
