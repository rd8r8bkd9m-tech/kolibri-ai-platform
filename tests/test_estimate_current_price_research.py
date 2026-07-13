from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from artifact_runtime import deterministic_estimate
import capability_gateway
import estimate_artifacts
import execution_api
import public_responses_api
import web_search_gateway
from estimate_artifacts import configure_estimate_artifact_store
from estimate_price_research import (
    EstimatePriceEvidenceError,
    _minor_values_from_quote,
    bind_price_provenance,
    bind_provider_asserted_price,
    build_citation_evidence_index,
    build_estimate_price_queries,
    source_matches_estimate_line,
)
from response_tool_gateway import execute_response_tools
from public_estimate_api import router as public_estimate_router
from provider_gateway import ProviderGateway, deterministic_verifier_evidence
from web_search_gateway import WebSearchUnavailable
from vertical_tasks import (
    EstimateProviderDraftError,
    estimate_spec_from_provider_response,
)


SOURCE_URL = "https://supplier.example/prices/aerated-block"
# Price evidence is intentionally accepted only within one UTC day of the
# request.  Keep the integration fixture current instead of letting a fixed
# calendar date turn the native-search contract into a midnight-dependent
# test failure.
CAPTURED = datetime.now(timezone.utc).date().isoformat()
QUOTE = "Газобетон D500: от 1 000 до 1 200 руб. за м³, доставка не включена."


def _runtime_state() -> dict:
    return {
        "capability": capability_gateway._gateway,
        "web": web_search_gateway._gateway,
        "public_store": public_responses_api._STORE,
        "public_executor": public_responses_api._EXECUTOR,
        "public_origins": public_responses_api._PUBLIC_ORIGINS,
        "execution_store": execution_api._store,
        "learning_boundary": execution_api._learning_boundary,
        "execution_keys": execution_api._EXECUTION_KEY_HASHES,
        "execution_auth_error": execution_api._EXECUTION_AUTH_CONFIGURATION_ERROR,
        "estimate_store": estimate_artifacts._STORE,
    }


def _restore_runtime_state(state: dict) -> None:
    capability_gateway._gateway = state["capability"]
    web_search_gateway._gateway = state["web"]
    public_responses_api._STORE = state["public_store"]
    public_responses_api._EXECUTOR = state["public_executor"]
    public_responses_api._PUBLIC_ORIGINS = state["public_origins"]
    execution_api._store = state["execution_store"]
    execution_api._learning_boundary = state["learning_boundary"]
    execution_api._EXECUTION_KEY_HASHES = state["execution_keys"]
    execution_api._EXECUTION_AUTH_CONFIGURATION_ERROR = state["execution_auth_error"]
    estimate_artifacts._STORE = state["estimate_store"]


def _citation(*, url: str = SOURCE_URL, quote: str = QUOTE) -> dict:
    title = "Прайс поставщика"
    snippet = f"Актуальный прайс. {quote}"
    return {
        "id": "cite_1",
        "title": title,
        "snippet": snippet,
        "url": url,
        "source_host": "supplier.example",
        "provider": "test-search",
        "retrieved_at": f"{CAPTURED}T09:30:00+00:00",
        "content_sha256": hashlib.sha256(json.dumps(
            {"title": title, "snippet": snippet, "url": url},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest(),
    }


def _draft(*, price_level_date: str = CAPTURED, source_url: str = SOURCE_URL) -> dict:
    return {
        "schema_version": "kolibri.estimate-provider-draft.v1",
        "title": "Предварительная смета дома",
        "currency": "RUB",
        "minor_unit": 2,
        "region": "Республика Татарстан, Лениногорск",
        "client_name": None,
        "object_name": "Одноэтажный дом 100 м²",
        "object_address": None,
        "source_summary": "Текущая коммерческая цена из контролируемого поиска; объём — допущение.",
        "normative_basis": {
            "calculation_method": "commercial",
            "normative_basis_ref": "Коммерческий ресурсный расчёт",
            "normative_edition": CAPTURED,
            "price_level_date": price_level_date,
            "region": "Республика Татарстан, Лениногорск",
            "index_document_refs": [],
            "tax_scope_ref": "НДС и режим поставщика требуют подтверждения",
            "contract_scope_ref": "Предварительный состав по пользовательскому брифу",
            "source_urls": [source_url],
            "input_document_refs": ["Пользовательский бриф: дом 100 м²"],
        },
        "sections": [{
            "id": "walls",
            "name": "Стены",
            "lines": [{
                "id": "material-block",
                "description": "Газобетон D500",
                "category": "material",
                "unit": "м³",
                "quantity": 2,
                # This provider assertion is accepted only because it lies in
                # the range; the engine selects the midpoint independently.
                "unit_price_minor": 105_000,
                "price_provenance": {
                    "source": "supplier",
                    "source_ref": "Прайс поставщика",
                    "source_url": source_url,
                    "captured_at": CAPTURED,
                    "price_level_date": price_level_date,
                    "applicable_region": "Республика Татарстан, Лениногорск",
                    "basis_ref": "Цена за м³",
                    "price_min_minor": 100_000,
                    "price_max_minor": 120_000,
                    "source_quote": QUOTE,
                    "source_item": "Газобетон D500",
                    "source_category": "material",
                    "source_unit": "м³",
                    "source_spec": "D500",
                    "assumptions": ["Доставка и разгрузка не включены; наличие требует подтверждения."],
                },
                "quantity_provenance": {
                    "source": "manual",
                    "source_ref": "Предварительное допущение по брифу 100 м²",
                    "source_url": None,
                    "assumptions": ["Объём заменить ведомостью по рабочему проекту."],
                },
                "assumptions": [],
            }],
        }],
        "assumptions": ["Смета предварительная до получения проекта и трёх коммерческих предложений."],
        "questions": ["Предоставьте проект и спецификацию стен."],
        "overhead_rate_bps": 0,
        "tax_rate_bps": 0,
    }


def test_dynamic_queries_cover_prices_labor_logistics_and_official_basis():
    queries = build_estimate_price_queries({
        "intent": "estimate",
        "brief": (
            "Составь настоящую предварительную смету для на строительство одноэтажного дома 100 м2 "
            "в Татарстане, Лениногорск, с актуальными ценами, источниками и PDF"
        ),
        "region": "Республика Татарстан, Лениногорск",
    }, today=date(2026, 7, 11))

    assert len(queries) == 4
    noise = ("составь", "настоящую", "предварительную", "смету", "актуальными", "источниками", "pdf")
    price_intent = ("цен", "стоимост", "расценк")
    assert all(not any(token in query.casefold() for token in noise) for query in queries)
    assert "строительство одноэтажного дома" in queries[0].casefold()
    assert "100 м²" not in queries[0]
    assert all("строительство одноэтажного дома 100 м²" in query.casefold() for query in queries[1:])
    assert all("республика татарстан" in query.casefold() for query in queries)
    assert "лениногорск" not in queries[0].casefold()
    assert all("лениногорск" in query.casefold() for query in queries[1:])
    assert all("в татарстане" not in query.casefold() for query in queries)
    assert all("100 м² республика" in query.casefold() for query in queries[1:])
    assert all("2026" in query for query in queries)
    assert all(any(token in query.casefold() for token in price_intent) for query in queries)
    assert any("под ключ" in query and "цена рублей за квадратный метр" in query for query in queries)
    assert any("материал" in query for query in queries)
    assert any("расценки работ" in query for query in queries)
    assert any("доставка логистика" in query for query in queries)
    assert any("fgiscs.minstroyrf.ru" in query for query in queries)
    assert any("текущий индекс сметной стоимости" in query for query in queries)
    assert all("2026-Q3" not in query for query in queries[:3])
    assert "2026-Q3" in queries[3]
    assert queries[0] == (
        "строительство одноэтажного дома Республика Татарстан под ключ "
        "цена рублей за квадратный метр 2026"
    )


def test_dynamic_queries_keep_another_object_and_do_not_invent_house_subject():
    queries = build_estimate_price_queries({
        "intent": "estimate",
        "brief": (
            "Подготовьте реальную смету PDF на ремонт кровли склада 800 кв. м "
            "с актуальными ценами и источниками"
        ),
        "region": "Самарская область, Самара",
    }, today=date(2026, 1, 9))

    assert len(queries) == 4
    assert "ремонт кровли склада 800 м²" not in queries[0].casefold()
    assert all("ремонт кровли склада 800 м²" in query.casefold() for query in queries[1:])
    assert all("самарская область" in query.casefold() for query in queries)
    assert all("2026-Q1" not in query for query in queries[:3])
    assert "2026-Q1" in queries[3]
    assert all(not re.search(r"\b(?:подготовьте|реальную|смету|актуальными|источниками|pdf)\b", query.casefold()) for query in queries)
    assert all("дом" not in query.casefold() for query in queries)


@pytest.mark.parametrize(
    ("brief", "region", "expected_market_query"),
    [
        (
            "Смета на строительство частного дома 120 м2",
            "Республика Башкортостан, Уфа",
            "строительство частного дома Республика Башкортостан под ключ цена рублей за квадратный метр 2026",
        ),
        (
            "Подготовь смету на ремонт кровли склада 800 м²",
            "Самарская область, Самара",
            "ремонт кровли склада Самарская область под ключ цена рублей за квадратный метр 2026",
        ),
    ],
)
def test_market_query_is_broad_without_live_search(brief, region, expected_market_query):
    queries = build_estimate_price_queries(
        {"intent": "estimate", "brief": brief, "region": region},
        today=date(2026, 8, 1),
    )

    assert queries[0] == expected_market_query
    assert region in queries[1]
    assert region in queries[2]
    assert region in queries[3]


def test_source_bound_provider_draft_uses_deterministic_range_midpoint():
    research: dict = {}
    spec = estimate_spec_from_provider_response(
        json.dumps(_draft(), ensure_ascii=False),
        requested_region="Республика Татарстан, Лениногорск",
        source_evidence=[_citation()],
        price_research_out=research,
        source_mode="controlled_search",
    )

    assert spec.lines[0].unit_price_minor == 110_000
    calculation = deterministic_estimate(spec)
    assert calculation["totals"]["grand_total_minor"] == 220_000
    assert research["status"] == "source_bound_preliminary"
    assert research["independent_normative_verification"] is False
    assert research["lines"][0]["price_min_minor"] == 100_000
    assert research["lines"][0]["price_max_minor"] == 120_000
    assert research["lines"][0]["selected_unit_price_minor"] == 110_000
    assert len(research["binding_sha256"]) == 64


@pytest.mark.parametrize(
    ("draft", "citation", "error_type"),
    [
        (_draft(source_url="https://invented.example/price"), _citation(), "price_evidence_invalid"),
        (_draft(price_level_date="2025-01-01"), _citation(), "price_evidence_invalid"),
    ],
)
def test_unbound_or_stale_price_is_rejected(draft, citation, error_type):
    with pytest.raises(EstimateProviderDraftError) as raised:
        estimate_spec_from_provider_response(
            json.dumps(draft, ensure_ascii=False),
            requested_region="Республика Татарстан, Лениногорск",
            source_evidence=[citation],
            source_mode="controlled_search",
        )
    assert raised.value.code == error_type


def test_quote_must_contain_every_range_boundary():
    one_boundary = "Газобетон D500: цена 1 000 руб. за м³"
    evidence = build_citation_evidence_index([_citation(quote=one_boundary)])
    provenance = _draft()["sections"][0]["lines"][0]["price_provenance"]
    provenance["source_quote"] = one_boundary
    with pytest.raises(EstimatePriceEvidenceError) as raised:
        bind_price_provenance(
            provenance=provenance,
            unit_price_minor=105_000,
            minor_unit=2,
            applicable_region="Республика Татарстан, Лениногорск",
            citation_index=evidence,
            field="lines.material-block",
            line_description="Газобетон D500",
            line_category="material",
            line_unit="м³",
        )
    assert raised.value.code == "price_range_not_in_source_quote"


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("Строительство дома: 125–145 тысяч рублей за квадратный метр", {12_500_000, 14_500_000}),
        ("Стоимость проекта: 6,5–14 млн ₽", {650_000_000, 1_400_000_000}),
        ("Стоимость проекта: 6.5–14 миллионов рублей", {650_000_000, 1_400_000_000}),
        ("Цена: 125 тыс. рублей", {12_500_000}),
        (
            "Строительство дома: 6,5–14 млн ₽; 125–145 тыс руб/м² в 2026 году",
            {650_000_000, 1_400_000_000, 12_500_000, 14_500_000},
        ),
    ],
)
def test_russian_price_scale_suffixes_are_structurally_bound(quote, expected):
    values = _minor_values_from_quote(quote, minor_unit=2)
    assert expected.issubset(values)


def test_price_scale_is_not_guessed_from_unbound_text():
    values = _minor_values_from_quote(
        "Цена 125–145 рублей. В соседнем абзаце упомянуты тысячи рублей.",
        minor_unit=2,
    )
    assert 12_500 in values
    assert 14_500 in values
    assert 12_500_000 not in values
    assert 14_500_000 not in values


def _square_metre_provenance(quote: str) -> dict:
    return {
        "source": "supplier",
        "source_ref": "Публикация о рынке ИЖС",
        "source_url": SOURCE_URL,
        "captured_at": CAPTURED,
        "price_level_date": CAPTURED,
        "applicable_region": "Республика Татарстан, Лениногорск",
        "basis_ref": "Цена за квадратный метр",
        "price_min_minor": 12_500_000,
        "price_max_minor": 14_500_000,
        "source_quote": quote,
        "source_item": "Строительство дома",
        "source_category": "labor",
        "source_unit": "м²",
        "source_spec": None,
        "assumptions": ["Коммерческий диапазон требует подтверждения предложениями подрядчиков."],
    }


def test_infox_like_square_metre_snippet_accepts_scaled_range_and_unit_alias():
    quote = (
        "Строительство дома под ключ оценивается в 125–145 тысяч рублей "
        "за квадратный метр."
    )
    evidence = build_citation_evidence_index([_citation(quote=quote)])
    selected, proof = bind_price_provenance(
        provenance=_square_metre_provenance(quote),
        unit_price_minor=13_500_000,
        minor_unit=2,
        applicable_region="Республика Татарстан, Лениногорск",
        citation_index=evidence,
        field="lines.house-shell",
        line_description="Строительство дома под ключ",
        line_category="labor",
        line_unit="м²",
    )
    assert selected == 13_500_000
    assert proof["price_min_minor"] == 12_500_000
    assert proof["price_max_minor"] == 14_500_000


@pytest.mark.parametrize(
    ("unit", "alias"),
    [
        ("м²", "квадратный метр"),
        ("м²", "квадратного метра"),
        ("м²", "кв метр"),
        ("м³", "кубический метр"),
        ("м³", "кубического метра"),
        ("м³", "куб метр"),
    ],
)
def test_russian_verbose_area_and_volume_unit_aliases(unit, alias):
    assert source_matches_estimate_line(
        line_description="Строительство дома под ключ",
        line_category="labor",
        line_unit=unit,
        source_item="Строительство дома",
        source_category="labor",
        source_unit=unit,
        source_spec=None,
        source_text=f"Строительство дома: цена за {alias}",
    )


def test_scaled_square_metre_snippet_rejects_unscaled_minor_values():
    quote = (
        "Строительство дома под ключ: цена квадратного метра составляет "
        "125–145 тысяч рублей."
    )
    provenance = _square_metre_provenance(quote)
    provenance["price_min_minor"] = 12_500
    provenance["price_max_minor"] = 14_500
    evidence = build_citation_evidence_index([_citation(quote=quote)])
    with pytest.raises(EstimatePriceEvidenceError) as raised:
        bind_price_provenance(
            provenance=provenance,
            unit_price_minor=13_500,
            minor_unit=2,
            applicable_region="Республика Татарстан, Лениногорск",
            citation_index=evidence,
            field="lines.house-shell",
            line_description="Строительство дома под ключ",
            line_category="labor",
            line_unit="м²",
        )
    assert raised.value.code == "price_range_not_in_source_quote"


def test_square_metre_line_rejects_cubic_metre_source_context():
    quote = (
        "Строительство дома под ключ оценивается в 125–145 тысяч рублей "
        "за кубический метр."
    )
    evidence = build_citation_evidence_index([_citation(quote=quote)])
    with pytest.raises(EstimatePriceEvidenceError) as raised:
        bind_price_provenance(
            provenance=_square_metre_provenance(quote),
            unit_price_minor=13_500_000,
            minor_unit=2,
            applicable_region="Республика Татарстан, Лениногорск",
            citation_index=evidence,
            field="lines.house-shell",
            line_description="Строительство дома под ключ",
            line_category="labor",
            line_unit="м²",
        )
    assert raised.value.code == "price_source_line_applicability_mismatch"


def test_controlled_price_for_gas_block_cannot_bind_to_roofing_square_metres():
    evidence = build_citation_evidence_index([_citation()])
    provenance = _draft()["sections"][0]["lines"][0]["price_provenance"]
    with pytest.raises(EstimatePriceEvidenceError) as raised:
        bind_price_provenance(
            provenance=provenance,
            unit_price_minor=105_000,
            minor_unit=2,
            applicable_region="Республика Татарстан, Лениногорск",
            citation_index=evidence,
            field="lines.roofing",
            line_description="Кровельное покрытие",
            line_category="material",
            line_unit="м²",
        )
    assert raised.value.code == "price_source_line_applicability_mismatch"


def test_native_provider_assertion_has_same_product_category_unit_gate():
    provenance = _draft()["sections"][0]["lines"][0]["price_provenance"]
    with pytest.raises(EstimatePriceEvidenceError) as raised:
        bind_provider_asserted_price(
            provenance=provenance,
            unit_price_minor=105_000,
            minor_unit=2,
            applicable_region="Республика Татарстан, Лениногорск",
            field="lines.roofing",
            citation_url_validator=lambda value: str(value),
            line_description="Монтаж кровельного покрытия",
            line_category="labor",
            line_unit="м²",
            observed_on=date(2026, 7, 11),
        )
    assert raised.value.code == "price_source_line_applicability_mismatch"


class _ResearchGateway:
    def __init__(self):
        self.queries: list[str] = []

    def execute(self, query, *, authorization, result_limit):
        self.queries.append(query)
        number = len(self.queries)
        url = f"https://supplier.example/price/{number}"
        citation = _citation(url=url, quote=f"Цена {number} 000 руб.")
        call = f"call_{number}"
        return {
            "provider_context": "unused generic context",
            "tool_call": {"call_id": call, "capability_id": "tool:web_search", "status": "succeeded"},
            "evidence": {"call_id": call, "type": "tool_execution", "output_sha256": "a" * 64},
            "citations": [citation],
            "attempts": [{"provider": "test", "status": "succeeded"}],
            "formulalm_tap": {"tool_id": "tool:web_search", "candidate_only": True},
        }


def test_response_tool_gateway_runs_dynamic_estimate_research(monkeypatch):
    gateway = _ResearchGateway()
    monkeypatch.setattr("response_tool_gateway.get_web_search_gateway", lambda: gateway)
    execution = execute_response_tools(
        input_value="Составь смету дома 100 м²",
        instructions=None,
        response_id="resp_current_prices",
        principal="public-session:test",
        requested_tools=[{"id": "tool:web_search"}],
        raw_tools=[{"type": "web_search", "search_context_size": "high"}],
        session_id="session_test",
        project_id="project_test",
        estimate_task={
            "intent": "estimate",
            "brief": "одноэтажный дом 100 м²",
            "region": "Республика Татарстан, Лениногорск",
        },
    )

    assert len(gateway.queries) == 4
    assert len(execution.tool_calls) == 4
    assert len(execution.citations) == 4
    assert "Current-price research evidence" in execution.provider_instructions
    assert f"Retrieved: {CAPTURED}" in execution.provider_instructions
    assert "copy source_quote exactly" in execution.provider_instructions


def test_estimate_research_normalizes_unexpected_gateway_failure(monkeypatch):
    class BrokenGateway:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("untrusted adapter detail")

    monkeypatch.setattr(
        "response_tool_gateway.get_web_search_gateway", lambda: BrokenGateway(),
    )
    execution = execute_response_tools(
        input_value="Составь смету дома 100 м²",
        instructions=None,
        response_id="resp_current_prices_failure",
        principal="public-session:test",
        requested_tools=[{"id": "tool:web_search"}],
        raw_tools=[{"type": "web_search", "search_context_size": "high"}],
        session_id="session_test",
        project_id="project_test",
        estimate_task={
            "intent": "estimate",
            "brief": "одноэтажный дом 100 м²",
            "region": "Республика Татарстан, Лениногорск",
        },
    )

    assert execution.tool_calls == []
    assert execution.provider_tools[0]["id"] == "tool:web_search"
    assert execution.attempts
    assert {item["error_type"] for item in execution.attempts} == {
        "web_search_provider_failed",
    }
    assert "untrusted adapter detail" not in str(execution)


class _CapabilityGateway:
    def validate_requested_tools(self, tools):
        return [{
            "id": "tool:web_search",
            "kind": "tool",
            "name": "web_search",
            "status": "available",
            "source": {"type": "packaged"},
            "_aliases": ("web_search",),
            "_providers": ("gateway",),
        }]


class _PriceWebGateway:
    def __init__(self):
        self.calls: list[str] = []

    def execute(self, query, *, authorization, result_limit):
        self.calls.append(query)
        call_id = f"price_call_{len(self.calls)}"
        citation = _citation()
        return {
            "provider_context": "generic context is replaced for estimate research",
            "tool_call": {
                "schema_version": "kolibri.tool-call.v1",
                "call_id": call_id,
                "capability_id": "tool:web_search",
                "tool": "web_search",
                "event_type": "web_search",
                "status": "succeeded",
            },
            "evidence": {
                "type": "tool_execution",
                "capability_id": "tool:web_search",
                "call_id": call_id,
                "output_sha256": "c" * 64,
            },
            "citations": [citation],
            "attempts": [{"provider": "test-search", "status": "succeeded"}],
            "formulalm_tap": {
                "schema_version": "kolibri.formulalm-tool-trace.v1",
                "tool_id": "tool:web_search",
                "candidate_only": True,
            },
        }


class _PriceDraftExecutor:
    def __init__(self):
        self.calls: list[dict] = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        text = json.dumps(_draft(), ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(text.encode()).hexdigest()
        evidence = [
            {
                "type": "provider_execution",
                "provider": "factory",
                "provider_model": "test-runner",
                "exit_code": 0,
                "output_sha256": digest,
                "output_bytes": len(text.encode()),
            },
            {
                "type": "deterministic_verifier",
                "verdict": "passed",
                "binding_sha256": "d" * 64,
            },
        ]
        return {
            "response": text,
            "model": "kolibri",
            "technical": {"provider_routing": {
                "selected_provider": "factory",
                "selected_runner": "test-runner",
                "attempts": [{"provider": "factory", "status": "succeeded"}],
                "evidence": evidence,
            }},
        }


def test_public_estimate_automatically_researches_prices_and_materializes_pdf(tmp_path):
    old_state = _runtime_state()
    executor = _PriceDraftExecutor()
    web = _PriceWebGateway()
    try:
        public_responses_api.configure_public_response_store(tmp_path / "public.db")
        public_responses_api.configure_public_response_origins(["http://testserver"])
        public_responses_api.configure_public_response_executor(executor)
        execution_api.configure_execution_store(tmp_path / "execution.db")
        execution_api.configure_execution_auth(["owner-key"])
        configure_estimate_artifact_store(
            tmp_path / "estimate.db", tmp_path / "estimate-artifacts",
        )
        capability_gateway.configure_capability_gateway(_CapabilityGateway())
        web_search_gateway.configure_web_search_gateway(web)
        app = FastAPI()
        app.include_router(public_responses_api.router)
        app.include_router(public_estimate_router)
        app.include_router(execution_api.router)
        client = TestClient(app)
        assert client.post(
            "/v1/public/session", headers={"Origin": "http://testserver"},
        ).status_code == 200
        response = client.post(
            "/v1/responses",
            headers={
                "Origin": "http://testserver",
                "Idempotency-Key": "current-price-estimate",
            },
            json={
                "model": "kolibri",
                "input": "Составь смету одноэтажного дома 100 м² Татарстан Лениногорск",
                # No manual tools declaration: estimate research is automatic.
                "task": {
                    "intent": "estimate",
                    "brief": "одноэтажный дом 100 м² Татарстан Лениногорск",
                    "region": "Республика Татарстан, Лениногорск",
                    "requested_artifacts": ["pdf"],
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["task"]["result"]["type"] == "deterministic_estimate"
        assert payload["task"]["result"]["status"] == "preliminary"
        assert payload["task"]["result"]["estimate"]["lines"][0]["unit_price_minor"] == 110_000
        assert payload["task"]["result"]["price_research"]["status"] == "source_bound_preliminary"
        assert payload["estimate_outcome"]["editor"]["available"] is True
        assert payload["estimate_outcome"]["pdf"]["status"] == "materialized"
        artifact = payload["estimate_outcome"]["pdf"]["artifact"]
        pdf = client.get(artifact["locator"])
        assert pdf.status_code == 200
        assert pdf.headers["content-type"].startswith("application/pdf")
        assert pdf.content.startswith(b"%PDF-")
        assert len(web.calls) == 4
        assert executor.calls
        assert "Current-price research evidence" in str(executor.calls[0]["messages"])
    finally:
        _restore_runtime_state(old_state)


class _NativeFallbackWebGateway:
    def __init__(self):
        self.calls: list[str] = []

    def execute(self, query, **_kwargs):
        self.calls.append(query)
        raise WebSearchUnavailable([{
            "provider": "controlled-search",
            "status": "failed",
            "error_type": "web_search_http_rejected",
        }])

    def _canonical_citation_url(self, value):
        text = str(value or "")
        return text if text == SOURCE_URL else None


class _NativePriceDraftExecutor(_PriceDraftExecutor):
    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        text = json.dumps(_draft(), ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(text.encode()).hexdigest()
        call_id = "native_web_search_call"
        verifier = {
            "type": "deterministic_verifier",
            "verdict": "passed",
            "binding_sha256": "e" * 64,
            "requested_tool_ids": ["tool:web_search"],
            "verified_tool_call_ids": [call_id],
        }
        return {
            "response": text,
            "model": "kolibri",
            "technical": {"provider_routing": {
                "selected_provider": "codex",
                "selected_runner": "codex",
                "tool_calls": [{
                    "call_id": call_id,
                    "tool": "web_search",
                    "capability_id": "tool:web_search",
                    "status": "succeeded",
                }],
                "verifier_evidence": verifier,
                "attempts": [{"provider": "codex", "status": "succeeded"}],
                "evidence": [
                    {
                        "type": "provider_execution",
                        "provider": "codex",
                        "provider_model": "test-runner",
                        "exit_code": 0,
                        "output_sha256": digest,
                        "output_bytes": len(text.encode()),
                    },
                    verifier,
                ],
            }},
        }


def test_native_codex_search_fallback_is_visible_but_never_claimed_verified(tmp_path):
    old_state = _runtime_state()
    executor = _NativePriceDraftExecutor()
    web = _NativeFallbackWebGateway()
    try:
        public_responses_api.configure_public_response_store(tmp_path / "public-native.db")
        public_responses_api.configure_public_response_origins(["http://testserver"])
        public_responses_api.configure_public_response_executor(executor)
        execution_api.configure_execution_store(tmp_path / "execution-native.db")
        execution_api.configure_execution_auth(["owner-key"])
        configure_estimate_artifact_store(
            tmp_path / "estimate-native.db", tmp_path / "estimate-native-artifacts",
        )
        capability_gateway.configure_capability_gateway(_CapabilityGateway())
        web_search_gateway.configure_web_search_gateway(web)
        app = FastAPI()
        app.include_router(public_responses_api.router)
        app.include_router(public_estimate_router)
        app.include_router(execution_api.router)
        client = TestClient(app)
        assert client.post(
            "/v1/public/session", headers={"Origin": "http://testserver"},
        ).status_code == 200
        response = client.post(
            "/v1/responses",
            headers={
                "Origin": "http://testserver",
                "Idempotency-Key": "native-current-price-estimate",
            },
            json={
                "model": "kolibri",
                "input": "Составь смету дома 100 м² Татарстан Лениногорск",
                "task": {
                    "intent": "estimate",
                    "brief": "одноэтажный дом 100 м² Татарстан Лениногорск",
                    "region": "Республика Татарстан, Лениногорск",
                    "requested_artifacts": ["pdf"],
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        research = payload["task"]["result"]["price_research"]
        assert payload["task"]["result"]["status"] == "preliminary"
        assert research["status"] == "provider_asserted_unverified"
        assert research["independent_normative_verification"] is False
        assert research["native_tool_binding"]["tool_call_ids"] == ["native_web_search_call"]
        assert payload["citations"][0]["verification_status"] == "provider_asserted_unverified"
        assert payload["citations"][0]["url"] == SOURCE_URL
        assert payload["tool_calls"][0]["tool"] == "web_search"
        assert payload["estimate_outcome"]["pdf"]["status"] == "materialized"
        assert executor.calls[0]["requested_tools"][0]["id"] == "tool:web_search"
        assert len(web.calls) == 4
    finally:
        _restore_runtime_state(old_state)


def _factory_native_search_task(*, binding_override: str | None = None) -> dict:
    response = "source-backed draft"
    task_id = "TASK-NATIVE-SEARCH"
    attempt_id = "attempt-native-search"
    fencing_token = 17
    evidence_sha = "a" * 64
    binding_payload = {
        "schema_version": "kolibri.native-web-search-evidence.v1",
        "task_id": task_id,
        "attempt_id": attempt_id,
        "fencing_token": fencing_token,
        "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
        "evidence_sha256": evidence_sha,
    }
    binding = hashlib.sha256(json.dumps(
        binding_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    return {
        "task_id": task_id,
        "state": "completed",
        "attempt_id": attempt_id,
        "fencing_token": fencing_token,
        "lease_owner": "node-a:agent-a",
        "result": {
            "status": "completed",
            "response": response,
            "attempt_id": attempt_id,
            "node_id": "node-a",
            "agent_id": "agent-a",
            "runner": "codex",
            "native_web_search_evidence": {
                "schema_version": "kolibri.native-web-search-evidence.v1",
                "tool": "web_search",
                "event_count": 2,
                "completed_event_count": 1,
                "query_count": 1,
                "query_sha256": ["b" * 64],
                "evidence_sha256": evidence_sha,
                "response_sha256": binding_payload["response_sha256"],
                "binding_sha256": binding_override or binding,
            },
        },
    }


def test_factory_native_search_evidence_projects_into_same_tool_verifier_contract():
    text, evidence, error = ProviderGateway._verify_factory_task(
        _factory_native_search_task(), node_id="node-a", runner="codex",
    )
    assert error is None and text == "source-backed draft"
    tool_calls = evidence["tool_calls"]
    verifier = deterministic_verifier_evidence(
        text,
        evidence,
        [{
            "id": "tool:web_search", "name": "web_search", "status": "available",
            "_aliases": ("web_search",),
        }],
        tool_calls,
    )
    assert verifier["verdict"] == "passed"
    assert verifier["verified_tool_call_ids"] == [tool_calls[0]["call_id"]]


def test_factory_native_search_binding_tamper_fails_closed():
    text, evidence, error = ProviderGateway._verify_factory_task(
        _factory_native_search_task(binding_override="f" * 64),
        node_id="node-a",
        runner="codex",
    )
    assert (text, evidence, error) == (
        "", None, "factory_native_web_search_evidence_invalid",
    )
