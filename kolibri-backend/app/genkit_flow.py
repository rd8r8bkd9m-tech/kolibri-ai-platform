"""Typed in-process Genkit Flow for Kolibri request orchestration."""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import HTTPException
from genkit import Genkit
from pydantic import BaseModel, Field


ai = Genkit()


class KolibriFlowMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(max_length=120_000)


class KolibriFlowInput(BaseModel):
    messages: list[KolibriFlowMessage] = Field(min_length=1, max_length=200)
    mode: Literal["chat", "fast", "deep"] = "chat"
    background: bool = False
    requested_tools: list[str] = Field(default_factory=list, max_length=50)


class KolibriFlowOutput(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    intent: Literal["chat", "estimate", "document"]
    task_type: Literal["chat", "fast", "analyze"]
    requires_sources: bool
    requires_server_calculation: bool
    direct_amounts_allowed: bool
    estimate_stage: Literal["not_applicable", "clarify", "research_and_calculate"]
    required_inputs: list[str] = Field(default_factory=list, max_length=10)
    planning_assumptions: list[str] = Field(default_factory=list, max_length=10)
    locale: Literal["ru-RU"] = "ru-RU"


_ESTIMATE_MARKERS = (
    re.compile(r"смет(?:а|у|ы|е|ой|ный|ную)", re.IGNORECASE),
    re.compile(
        r"рассч(?:итай|итать|ёт|ета|ете).{0,80}(?:работ|материал|ремонт|строител)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:^|\s)(?:лср|вор|кс-2|кс-3)(?:\s|$)", re.IGNORECASE),
)
_DOCUMENT_MARKERS = (
    re.compile(
        r"(?:договор|акт|сч[её]т|коммерческ(?:ое|ого) предложени[ея])|"
        r"(?:^|\s)кп(?:\s|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:составь|подготовь|создай).{0,80}"
        r"(?:документ|письмо|меморандум|отч[её]т)",
        re.IGNORECASE,
    ),
)


def _latest_user_text(messages: list[KolibriFlowMessage]) -> str:
    return next(
        (
            message.content.strip()
            for message in reversed(messages)
            if message.role == "user"
        ),
        "",
    )


def _missing_estimate_inputs(text: str) -> list[str]:
    missing: list[str] = []
    if not re.search(r"\d+(?:[.,]\d+)?\s*(?:м\s*[²³23]|кв\.?\s*м|шт\.?|п\.?\s*м)", text, re.IGNORECASE):
        missing.append("объёмы и единицы измерения")
    if not re.search(r"(?:\bв\s+[А-ЯЁ][а-яё-]{2,}|город|област|край|республик|район)", text):
        missing.append("город и регион объекта")
    if not re.search(r"(?:материал|газобетон|кирпич|каркас|монолит|бетон|гипс|цемент|профлист|марка|класс)", text, re.IGNORECASE):
        missing.append("конструктив, материалы и требуемое качество")
    if not re.search(r"(?:под ключ|только работ|работы и материалы|без материал|включая|исключая)", text, re.IGNORECASE):
        missing.append("границы сметы: работы, материалы, доставка и оборудование")
    return missing


def _estimate_intent(messages: list[KolibriFlowMessage]) -> bool:
    """Recognise both a new estimate and a substantive answer to its brief."""

    latest_index = next(
        (index for index in range(len(messages) - 1, -1, -1) if messages[index].role == "user"),
        None,
    )
    if latest_index is None:
        return False
    latest = messages[latest_index].content.strip()
    if any(pattern.search(latest) for pattern in _ESTIMATE_MARKERS):
        return True
    if not re.search(
        r"(?:\d|этаж|фундамент|стен|кров|газобет|кирпич|каркас|монолит|"
        r"регион|город|материал|под ключ|короб|ндс|электр|отоп|вод|канал|"
        r"(?:^|\s)(?:да|нет)(?:\s|$))",
        latest,
        re.IGNORECASE,
    ):
        return False
    for index in range(latest_index - 1, -1, -1):
        message = messages[index]
        if message.role == "user" and any(
            pattern.search(message.content) for pattern in _ESTIMATE_MARKERS
        ):
            return any(
                candidate.role == "assistant"
                and re.search(r"смет|уточн|исходн.*данн|вопрос", candidate.content, re.IGNORECASE)
                for candidate in messages[index + 1 : latest_index]
            )
    return False


@ai.flow()
async def kolibri_chat_orchestration_flow(
    input: KolibriFlowInput,
) -> KolibriFlowOutput:
    """Plan one request before Kolibri selects its MIMA/provider route."""

    text = _latest_user_text(input.messages)
    if _estimate_intent(input.messages):
        intent: Literal["chat", "estimate", "document"] = "estimate"
    elif any(pattern.search(text) for pattern in _DOCUMENT_MARKERS):
        intent = "document"
    else:
        intent = "chat"

    task_type: Literal["chat", "fast", "analyze"]
    if input.mode == "deep" or intent == "estimate":
        task_type = "analyze"
    else:
        task_type = input.mode

    estimate = intent == "estimate"
    planning_assumptions = _missing_estimate_inputs(text) if estimate else []
    return KolibriFlowOutput(
        intent=intent,
        task_type=task_type,
        requires_sources=estimate,
        requires_server_calculation=estimate,
        direct_amounts_allowed=not estimate,
        # A professional estimator must produce an editable preliminary result
        # even when the brief is incomplete. Missing fields become visible
        # assumptions; they no longer block the calculation with a questionnaire.
        estimate_stage="research_and_calculate" if estimate else "not_applicable",
        required_inputs=[],
        planning_assumptions=planning_assumptions,
    )


def _base_mode(policy: dict[str, Any] | None) -> Literal["chat", "fast", "deep"]:
    if policy and policy.get("mode") == "deep":
        return "deep"
    if policy:
        return "fast"
    return "chat"


async def plan_kolibri_request(
    messages: list[dict[str, str]],
    policy: dict[str, Any] | None,
    *,
    background: bool = False,
) -> KolibriFlowOutput:
    try:
        flow_input = KolibriFlowInput(
            messages=[
                KolibriFlowMessage(
                    role=(
                        message.get("role")
                        if message.get("role") in {"system", "user", "assistant", "tool"}
                        else "user"
                    ),
                    content=str(message.get("content") or "")[:120_000],
                )
                for message in messages[:200]
            ],
            mode=_base_mode(policy),
            background=background,
            requested_tools=[
                str(item)[:100]
                for item in (policy or {}).get("allowed_capabilities", [])[:50]
            ],
        )
        result = await kolibri_chat_orchestration_flow(flow_input)
    except Exception:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "genkit_flow_unavailable",
                "message": "AI orchestration is temporarily unavailable",
                "recoverable": True,
            },
        ) from None

    if result.intent == "estimate" and (
        result.direct_amounts_allowed
        or not result.requires_sources
        or not result.requires_server_calculation
    ):
        raise HTTPException(
            status_code=503,
            detail={"code": "genkit_flow_unsafe_estimate_plan", "recoverable": True},
        )
    return result


async def planned_task_type(
    messages: list[dict[str, str]],
    policy: dict[str, Any] | None,
    *,
    background: bool = False,
) -> str:
    return (await plan_kolibri_request(
        messages,
        policy,
        background=background,
    )).task_type
