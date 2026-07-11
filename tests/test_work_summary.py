from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from work_summary import (  # noqa: E402
    METADATA_KEY,
    POLICY_METADATA_KEY,
    SOURCES_METADATA_KEY,
    build_work_summary,
    reasoning_output_item,
    summary_from_metadata,
    summary_metadata,
)
from public_responses_api import _decorate_response_work_summary  # noqa: E402


def test_work_summary_is_allowlisted_and_never_copies_prompts_or_secrets():
    secret = "sk-never-expose-work-summary-123456"
    raw_prompt = "RAW PRIVATE USER PROMPT"
    summary = build_work_summary(
        response_status="completed",
        task={"intent": "estimate", "brief": raw_prompt, "api_key": secret},
        requested_tools=[{"type": "web_search", "arguments": raw_prompt}],
        tool_calls=[{
            "capability_id": "tool:web_search",
            "arguments": {"authorization": f"Bearer {secret}"},
            "result": raw_prompt,
        }],
        citations=[{
            "url": f"https://prices.example/token/{secret}?token={secret}",
            "title": raw_prompt,
            "snippet": secret,
        }, {
            "url": "http://10.99.0.2:9101/internal",
            "source_host": "10.99.0.2",
        }],
        verification={
            "status": "passed",
            "raw_reasoning": raw_prompt,
            "authorization": secret,
        },
    )

    serialized = json.dumps(summary, ensure_ascii=False)
    assert summary["schema_version"] == "kolibri.work-summary.v1"
    assert summary["mode"] == "summary_only"
    assert summary["raw_reasoning_exposed"] is False
    assert [item["kind"] for item in summary["items"]] == [
        "plan", "tool", "source", "check", "verdict",
    ]
    assert secret not in serialized
    assert raw_prompt not in serialized
    assert "prices.example" in serialized
    assert "10.99.0.2" not in serialized
    assert "?token=" not in serialized
    assert "Веб-поиск" in serialized
    source = next(item for item in summary["items"] if item["kind"] == "source")
    assert source["sources"][0]["url"] == "https://prices.example/"


def test_openai_metadata_is_string_bounded_and_reasoning_item_is_summary_only():
    summary = build_work_summary(
        response_status="completed",
        requested_tools=[],
        tool_calls=[],
        citations=[],
        verification={"verdict": "passed"},
    )
    metadata = summary_metadata({"client": "shell"}, summary)

    assert metadata["client"] == "shell"
    assert isinstance(metadata[METADATA_KEY], str)
    assert len(metadata[METADATA_KEY]) <= 512
    assert metadata[POLICY_METADATA_KEY] == "summary_only_no_raw_chain_of_thought"
    compact = json.loads(metadata[METADATA_KEY])
    assert compact["v"] == 1
    assert compact["mode"] == "summary_only"
    assert len(compact["items"]) == 5

    reasoning = reasoning_output_item("resp_test", summary)
    assert reasoning["type"] == "reasoning"
    assert reasoning["id"].startswith("rs_")
    assert len(reasoning["summary"]) == 5
    assert all(part["type"] == "summary_text" for part in reasoning["summary"])
    assert "content" not in reasoning
    assert "encrypted_content" not in reasoning


def test_unused_tools_and_sources_are_reported_as_connected_not_missing():
    summary = build_work_summary(
        response_status="completed",
        verification={"status": "passed"},
    )
    by_kind = {item["kind"]: item for item in summary["items"]}
    assert by_kind["tool"] == {
        "kind": "tool",
        "status": "available",
        "detail": "Инструментальный контур подключён; для этого запроса вызов не потребовался.",
    }
    assert by_kind["source"] == {
        "kind": "source",
        "status": "available",
        "detail": "Контур источников подключён; для этого запроса ссылки не использовались.",
    }


def test_preliminary_estimate_projects_source_domains_and_price_dates():
    summary = build_work_summary(
        response_status="completed",
        task={
            "intent": "estimate",
            "status": "completed",
            "result": {
                "type": "deterministic_estimate",
                "status": "preliminary",
                "estimate": {
                    "normative_basis": {
                        "source_urls": ["https://minstroyrf.gov.ru/prices"],
                        "price_level_date": "2026-Q2",
                    },
                    "lines": [{
                        "provenance": {
                            "source_url": "https://supplier.example/catalog",
                            "captured_at": "2026-07-11",
                            "price_level_date": "2026-Q2",
                        },
                    }],
                },
            },
        },
        verification={"status": "passed"},
    )
    source = next(item for item in summary["items"] if item["kind"] == "source")
    assert source["status"] == "incomplete"
    assert "Источники указаны: 2" in source["detail"]
    assert "minstroyrf.gov.ru" in source["detail"]
    assert "supplier.example" in source["detail"]
    assert "2026-Q2" in source["detail"]
    by_kind = {item["kind"]: item for item in summary["items"]}
    assert by_kind["check"]["status"] == "incomplete"
    assert "независимая проверка" in by_kind["check"]["detail"]
    assert by_kind["verdict"]["status"] == "incomplete"
    assert "Предварительная смета" in by_kind["verdict"]["detail"]
    assert "Проверенный результат готов" not in json.dumps(summary, ensure_ascii=False)
    assert source["sources"] == [
        {
            "url": "https://minstroyrf.gov.ru/prices",
            "domain": "minstroyrf.gov.ru",
            "price_level_date": "2026-Q2",
        },
        {
            "url": "https://supplier.example/catalog",
            "domain": "supplier.example",
            "price_level_date": "2026-Q2",
            "captured_at": "2026-07-11",
        },
    ]
    metadata = summary_metadata({}, summary)
    encoded_sources = metadata[SOURCES_METADATA_KEY]
    assert len(encoded_sources) <= 512
    assert json.loads(encoded_sources)["sources"] == source["sources"]
    assert summary_from_metadata(metadata)["items"][2]["sources"] == source["sources"]


def test_estimate_missing_required_sources_remains_blocked():
    summary = build_work_summary(
        response_status="completed",
        task={
            "intent": "estimate",
            "status": "completed",
            "result": {
                "type": "deterministic_estimate",
                "status": "preliminary",
                "estimate": {"lines": []},
                "verification": {
                    "source_coverage_complete": False,
                    "coverage_missing": ["normative_basis.source_urls"],
                },
            },
        },
        verification={"status": "passed"},
    )
    by_kind = {item["kind"]: item for item in summary["items"]}
    assert by_kind["source"]["status"] == "blocked"
    assert "обязательных ссылок" in by_kind["source"]["detail"]
    assert by_kind["check"]["status"] == "blocked"
    assert by_kind["verdict"]["status"] == "incomplete"
    assert "Проверенный результат готов" not in json.dumps(summary, ensure_ascii=False)


def test_source_projection_rejects_invalid_numeric_host_and_invalid_date():
    summary = build_work_summary(
        response_status="completed",
        task={
            "intent": "estimate",
            "status": "completed",
            "result": {
                "type": "deterministic_estimate",
                "status": "preliminary",
                "estimate": {"lines": [{"provenance": {
                    "source_url": "https://source.example/catalog",
                    "captured_at": "2026-99-99",
                }}]},
                "verification": {"source_coverage_complete": True, "coverage_missing": []},
            },
        },
        citations=[{"url": "https://999.999.999.999/catalog"}],
        verification={"status": "passed"},
    )
    source = next(item for item in summary["items"] if item["kind"] == "source")
    assert all(item["domain"] != "999.999.999.999" for item in source.get("sources", []))
    assert source["sources"] == [{
        "url": "https://source.example/catalog",
        "domain": "source.example",
    }]


def test_in_progress_summary_has_truthful_nonterminal_states():
    summary = build_work_summary(
        response_status="in_progress",
        requested_tools=[{"type": "web_search"}],
    )
    statuses = {item["kind"]: item["status"] for item in summary["items"]}
    assert statuses == {
        "plan": "running",
        "tool": "pending",
        "source": "pending",
        "check": "pending",
        "verdict": "pending",
    }


def test_estimate_readiness_envelope_never_claims_verified_or_ready_money():
    summary = build_work_summary(
        response_status="completed",
        task={
            "schema_version": "kolibri.public-task.v1",
            "intent": "estimate",
            "status": "incomplete",
            "result": {
                "type": "estimate_readiness",
                "readiness": {
                    "status": "needs_input",
                    "known_facts": {"region": "Республика Татарстан"},
                },
            },
        },
        requested_tools=[],
        tool_calls=[],
        citations=[],
        # The response envelope itself can be content-bound while the money
        # gate remains incomplete. This verdict must not upgrade task truth.
        verification={"status": "passed", "type": "deterministic_estimate_readiness"},
    )

    by_kind = {item["kind"]: item for item in summary["items"]}
    assert by_kind["plan"]["status"] == "incomplete"
    assert "Черновик исходных данных" in by_kind["plan"]["detail"]
    assert by_kind["source"]["status"] == "blocked"
    assert "подтверждённые источники" in by_kind["source"]["detail"]
    assert by_kind["check"]["status"] == "blocked"
    assert "ожидает исходных данных" in by_kind["check"]["detail"]
    assert by_kind["verdict"]["status"] == "incomplete"
    assert "денежный итог не рассчитан" in by_kind["verdict"]["detail"]
    serialized = json.dumps(summary, ensure_ascii=False)
    assert "Проверка результата пройдена" not in serialized
    assert "Проверенный результат готов" not in serialized


def test_owner_response_decorator_projects_only_allowlisted_lifecycle_facts():
    secret = "sk-owner-internal-never-public-123"
    response = _decorate_response_work_summary({
        "id": "resp_owner",
        "status": "completed",
        "metadata": {"client": "owner"},
        "tools": [{"id": "tool:web_search"}],
        "citations": [{"url": f"https://source.example/x?token={secret}"}],
        "output": [{
            "id": "msg_owner",
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "answer", "annotations": []}],
        }],
        "technical": {"provider_routing": {
            "selected_provider": secret,
            "tool_calls": [{
                "capability_id": "tool:web_search",
                "arguments": {"authorization": secret},
            }],
            "verifier_evidence": {"verdict": "passed", "raw_reasoning": secret},
        }},
    })

    projected = json.dumps({
        "metadata": response["metadata"],
        "reasoning": next(item for item in response["output"] if item["type"] == "reasoning"),
    })
    assert secret not in projected
    assert "source.example" in projected
    assert response["metadata"]["client"] == "owner"
