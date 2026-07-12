from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import main
from providers import ProviderGatewayError


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _verified_routing(text: str, *, refs=None, extra_evidence=None):
    evidence = [
        {
            "type": "provider_execution",
            "provider": "factory",
            "provider_model": "mimo",
            "route_transport": "home_control_plane",
            "exit_code": 0,
            "output_sha256": _sha(text),
            "output_bytes": len(text.encode("utf-8")),
            "completion_signal": "fenced_non_empty_assistant_output",
        },
        {
            "type": "deterministic_verifier",
            "verifier": "kolibri.gateway.contract.v1",
            "verdict": "passed",
            "binding_sha256": "b" * 64,
        },
        *(extra_evidence or []),
    ]
    return {
        "selected_provider": "factory",
        "selected_runner": "mimo",
        "attempts": [{"attempt": 1, "provider": "factory", "status": "succeeded"}],
        "fallback_used": False,
        "artifact_refs": refs or [],
        "evidence": evidence,
    }


class FakeManager:
    def __init__(self, text="Готов проверенный результат.", *, refs=None, extra_evidence=None):
        self.text = text
        self.refs = refs
        self.extra_evidence = extra_evidence
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "response": self.text,
            "model": "kolibri",
            "technical": {
                "provider_routing": _verified_routing(
                    self.text,
                    refs=self.refs,
                    extra_evidence=self.extra_evidence,
                )
            },
        }


def _client(monkeypatch, manager):
    monkeypatch.setattr(main, "ai_manager", manager)
    monkeypatch.setattr(main, "check_rate_limit", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main, "get_cached_response", lambda _key: None)
    monkeypatch.setattr(
        main,
        "cache_response",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("typed tasks must not use text cache")),
    )
    return TestClient(main.app)


def _estimate_task(*, requested_artifacts=None):
    return {
        "intent": "estimate",
        "spec": {
            "title": "Ремонт кухни",
            "currency": "RUB",
            "minor_unit": 2,
            "region": "Москва",
            "normative_basis": {
                "calculation_method": "resource",
                "normative_basis_ref": "TEST-NORMATIVE-BASE-2026",
                "normative_edition": "Тестовая редакция 2026-01-01",
                "price_level_date": "2026-01-01",
                "region": "Москва",
                "index_document_refs": [],
                "tax_scope_ref": "TEST-TAX-SCOPE-2026",
                "contract_scope_ref": "TEST-CONTRACT-SCOPE-2026",
            },
            "lines": [
                {
                    "id": "labor-1",
                    "description": "Монтаж",
                    "category": "labor",
                    "unit": "м2",
                    "quantity": "2",
                    "unit_price_minor": 15_000,
                    "provenance": {
                        "source": "normative",
                        "source_ref": "TEST-PRICE-SOURCE-LABOR",
                        "captured_at": "2026-01-01",
                        "applicable_region": "Москва",
                        "price_level_date": "2026-01-01",
                        "basis_ref": "TEST-BASIS-LABOR",
                        "quantity_source": "project",
                        "quantity_source_ref": "TEST-PROJECT-SHEET-LABOR",
                    },
                },
                {
                    "id": "material-1",
                    "description": "Материал",
                    "category": "material",
                    "unit": "шт",
                    "quantity": "3",
                    "unit_price_minor": 5_000,
                    "provenance": {
                        "source": "supplier",
                        "source_ref": "quote-17",
                        "captured_at": "2026-01-01",
                        "applicable_region": "Москва",
                        "price_level_date": "2026-01-01",
                        "basis_ref": "TEST-BASIS-MATERIAL",
                        "quantity_source": "project",
                        "quantity_source_ref": "TEST-PROJECT-SHEET-MATERIAL",
                    },
                },
            ],
            "overhead_rate_bps": 1_000,
            "tax_rate_bps": 2_000,
        },
        "requested_artifacts": requested_artifacts or [],
    }


def test_public_estimate_uses_home_gateway_and_deterministic_money(monkeypatch):
    manager = FakeManager("Смета рассчитана по переданным строкам.")
    response = _client(monkeypatch, manager).post(
        "/api/v1/chat",
        json={
            "messages": [{"role": "user", "content": "Рассчитай смету"}],
            "model": "kolibri",
            "task": _estimate_task(),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "kolibri"
    assert "provider" not in payload
    assert payload["cached"] is False
    task = payload["task"]
    assert task["intent"] == "estimate"
    assert task["status"] == "completed"
    assert task["execution"]["provider_verified"] is True
    calculation = task["result"]["calculation"]
    assert calculation["engine"] == "kolibri.decimal-minor-unit.v1"
    assert calculation["totals"] == {
        "categories_minor": {"labor": 30_000, "material": 15_000},
        "subtotal_minor": 45_000,
        "overhead_minor": 4_500,
        "taxable_minor": 49_500,
        "tax_minor": 9_900,
        "grand_total_minor": 59_400,
    }
    assert calculation["money_authority"] == "deterministic_calculator"
    assert calculation["llm_calculates_money"] is False
    assert task["artifact_delivery"]["status"] == "not_required"
    outcome = payload["estimate_outcome"]
    assert outcome["status"] == task["result"]["status"]
    assert outcome["status"] in {"verified", "preliminary"}
    assert outcome["pricing"]["money_authority"] == "deterministic_calculator"
    assert outcome["pricing"]["invented_prices"] is False
    assert outcome["editor"]["available"] is True
    assert outcome["editor"]["mode"] == "estimate"
    assert outcome["pdf"] == {
        "requested": False,
        "status": "not_requested",
        "artifact": None,
    }
    assert len(manager.calls) == 1
    system_messages = [
        message["content"] for message in manager.calls[0]["messages"]
        if message["role"] == "system"
    ]
    assert any("authoritative_calculation" in value for value in system_messages)
    assert any("home" in item.get("route_transport", "") for item in payload["technical"]["provider_routing"]["evidence"])


def test_site_response_does_not_invent_artifact_from_a_path_mention(monkeypatch):
    bogus_ref = {
        "kind": "file",
        "name": "site.zip",
        "locator": "artifact://mention/site.zip",
        "reference_sha256": "a" * 64,
        "content_sha256": "c" * 64,
        "size_bytes": 1_024,
    }
    manager = FakeManager("Подготовлен план реализации сайта.", refs=[bogus_ref])
    response = _client(monkeypatch, manager).post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "Сделай сайт"}],
            "task": {
                "intent": "site",
                "brief": "Премиальный сайт строительной компании",
                "target": "website",
            },
        },
    )

    assert response.status_code == 200
    task = response.json()["task"]
    assert task["execution"]["status"] == "completed"
    assert task["status"] == "incomplete"
    assert task["artifacts"] == []
    assert task["artifact_delivery"]["status"] == "not_materialized"
    assert task["artifact_delivery"]["missing"] == ["source", "site-preview"]


def test_document_is_completed_only_with_content_bound_materialization(monkeypatch):
    ref = {
        "kind": "file",
        "name": "offer.pdf",
        "locator": "artifact://verified/offer.pdf",
        "media_type": "application/pdf",
        "reference_sha256": "a" * 64,
        "content_sha256": "c" * 64,
        "size_bytes": 12_345,
    }
    materialization = {
        "type": "artifact_materialization",
        "verdict": "passed",
        "deliverable_type": "pdf",
        "reference_sha256": "a" * 64,
        "content_sha256": "c" * 64,
        "size_bytes": 12_345,
        "binding_sha256": "d" * 64,
    }
    manager = FakeManager(
        "Документ создан и подтверждён.",
        refs=[ref],
        extra_evidence=[materialization],
    )
    response = _client(monkeypatch, manager).post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "Сделай КП"}],
            "task": {
                "intent": "document",
                "brief": "Коммерческое предложение на ремонт",
                "document_type": "commercial-offer",
                "format": "pdf",
            },
        },
    )

    assert response.status_code == 200
    task = response.json()["task"]
    assert task["status"] == "completed"
    assert task["artifact_delivery"]["status"] == "materialized"
    assert task["artifact_delivery"]["missing"] == []
    assert task["artifacts"] == [{
        "kind": "file",
        "name": "offer.pdf",
        "locator": "artifact://verified/offer.pdf",
        "media_type": "application/pdf",
        "reference_sha256": "a" * 64,
        "content_sha256": "c" * 64,
        "size_bytes": 12_345,
        "deliverable_type": "pdf",
        "evidence_binding_sha256": "d" * 64,
        "status": "materialized",
    }]


def test_app_with_partial_artifacts_remains_incomplete(monkeypatch):
    ref = {
        "kind": "file",
        "name": "source.zip",
        "locator": "artifact://verified/source.zip",
        "reference_sha256": "1" * 64,
        "content_sha256": "2" * 64,
        "size_bytes": 500,
    }
    proof = {
        "type": "artifact_materialization",
        "verdict": "passed",
        "deliverable_type": "source",
        "reference_sha256": "1" * 64,
        "content_sha256": "2" * 64,
        "size_bytes": 500,
        "binding_sha256": "3" * 64,
    }
    task = _client(monkeypatch, FakeManager("Исходники подготовлены.", refs=[ref], extra_evidence=[proof])).post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "Сделай приложение"}],
            "task": {"intent": "app", "brief": "CRM для подрядчика", "target": "web"},
        },
    ).json()["task"]

    assert task["status"] == "incomplete"
    assert task["artifact_delivery"]["delivered"] == ["source"]
    assert task["artifact_delivery"]["missing"] == ["build", "test-report"]
    assert task["artifacts"][0]["status"] == "materialized"


def test_artifact_proof_for_different_provider_output_is_rejected(monkeypatch):
    ref = {
        "kind": "file",
        "name": "offer.pdf",
        "locator": "artifact://verified/offer.pdf",
        "reference_sha256": "a" * 64,
        "content_sha256": "c" * 64,
        "size_bytes": 12_345,
    }
    proof = {
        "type": "artifact_materialization",
        "verdict": "passed",
        "deliverable_type": "pdf",
        "reference_sha256": "a" * 64,
        "content_sha256": "c" * 64,
        "size_bytes": 12_345,
        "binding_sha256": "d" * 64,
    }

    class MismatchedManager:
        async def generate(self, **_kwargs):
            return {
                "response": "Другой ответ",
                "model": "kolibri",
                "technical": {
                    "provider_routing": _verified_routing(
                        "Ответ, к которому привязано доказательство",
                        refs=[ref],
                        extra_evidence=[proof],
                    )
                },
            }

    task = _client(monkeypatch, MismatchedManager()).post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "Сделай документ"}],
            "task": {"intent": "document", "brief": "КП", "format": "pdf"},
        },
    ).json()["task"]

    assert task["status"] == "failed"
    assert task["execution"]["provider_verified"] is False
    assert task["artifacts"] == []


def test_vertical_provider_failure_is_typed_and_fail_closed(monkeypatch):
    class FailedManager:
        async def generate(self, **_kwargs):
            raise ProviderGatewayError({"error_type": "factory_control_unavailable", "attempts": []})

    response = _client(monkeypatch, FailedManager()).post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "Сделай сайт"}],
            "task": {"intent": "site", "brief": "Сайт компании"},
        },
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["model"] == "kolibri"
    assert payload["task"]["status"] == "failed"
    assert payload["task"]["artifacts"] == []
    assert payload["task"]["execution"]["provider_verified"] is False


def test_legacy_chat_reuses_truthful_non_monetary_house_readiness_gate(monkeypatch):
    class FailedManager:
        async def generate(self, **_kwargs):
            raise ProviderGatewayError({
                "error_type": "provider_timeout",
                "attempts": [{
                    "attempt": 1,
                    "status": "failed",
                    "error_type": "provider_timeout",
                }],
            })

    brief = "Составь смету на строительство одноэтажного дома 100 м2 Татарстан Лениногорск"
    response = _client(monkeypatch, FailedManager()).post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": brief}],
            "task": {
                "intent": "estimate",
                "brief": brief,
                "requested_artifacts": ["pdf"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "kolibri"
    assert "Денежный итог не рассчитан" in payload["response"]
    task = payload["task"]
    assert task["status"] == "incomplete"
    assert task["execution"]["provider_verified"] is False
    assert task["execution"]["engine_verified"] is True
    assert task["artifact_delivery"]["missing"] == ["pdf"]
    assert task["result"]["type"] == "estimate_readiness"
    assert task["result"]["readiness"]["status"] == "needs_input"
    assert task["result"]["readiness"]["monetary_status"] == "not_calculated"
    assert "calculation" not in task["result"]
    outcome = payload["estimate_outcome"]
    assert outcome["status"] == "needs_input"
    assert outcome["pricing"] == {
        "status": "not_calculated",
        "invented_prices": False,
    }
    assert outcome["editor"]["available"] is True
    assert outcome["editor"]["mode"] == "input_requirements"
    assert outcome["pdf"] == {
        "requested": True,
        "status": "not_materialized",
        "artifact": None,
    }


def test_public_vertical_payload_rejects_raw_secrets(monkeypatch):
    response = _client(monkeypatch, FakeManager()).post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "Сделай сайт"}],
            "task": {
                "intent": "site",
                "brief": "Сайт компании",
                "requirements": {"api_key": "must-not-enter-task-contract"},
            },
        },
    )

    assert response.status_code == 422
