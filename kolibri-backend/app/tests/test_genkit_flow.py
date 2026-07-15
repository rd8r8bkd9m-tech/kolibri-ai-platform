import asyncio

import pytest
from fastapi import HTTPException

from app import genkit_flow


def test_genkit_flow_routes_estimate_to_verified_server_calculation():
    result = asyncio.run(genkit_flow.plan_kolibri_request(
        [{"role": "user", "content": "Составь смету на штукатурку 420 м² в Казани"}],
        {"mode": "fast", "allowed_capabilities": ["web_search"]},
    ))

    assert result.intent == "estimate"
    assert result.task_type == "analyze"
    assert result.requires_sources is True
    assert result.requires_server_calculation is True
    assert result.direct_amounts_allowed is False
    assert result.estimate_stage == "clarify"
    assert "конструктив, материалы и требуемое качество" in result.required_inputs


def test_genkit_flow_allows_research_only_after_estimate_brief_is_complete():
    result = asyncio.run(genkit_flow.plan_kolibri_request(
        [{"role": "user", "content": (
            "Составь смету в Казани: штукатурка цементная 420 м², работы и материалы, "
            "включая доставку"
        )}],
        {"mode": "fast", "allowed_capabilities": ["web_search"]},
    ))

    assert result.intent == "estimate"
    assert result.estimate_stage == "research_and_calculate"
    assert result.required_inputs == []


def test_genkit_flow_keeps_fast_chat_fast():
    assert asyncio.run(genkit_flow.planned_task_type(
        [{"role": "user", "content": "Объясни разницу между гипсом и цементом"}],
        {"mode": "fast"},
    )) == "fast"


def test_genkit_flow_failure_is_visible(monkeypatch):
    async def broken_flow(_input):
        raise RuntimeError("offline")

    monkeypatch.setattr(genkit_flow, "kolibri_chat_orchestration_flow", broken_flow)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(genkit_flow.planned_task_type(
            [{"role": "user", "content": "Привет"}],
            None,
        ))
    assert caught.value.status_code == 503
    assert caught.value.detail["code"] == "genkit_flow_unavailable"
