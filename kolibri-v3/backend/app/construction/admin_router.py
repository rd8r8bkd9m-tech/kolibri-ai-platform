"""Owner control plane for construction-module professional Agent Cards."""

from __future__ import annotations

import re
import sqlite3
import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field, model_validator

from ..database import get_database, transaction
from ..identity import require_owner
from ..schemas import APIModel, UserSession
from ..security import require_mutation_auth
from .agents import ALL_CONSTRUCTION_AGENTS, ConstructionAgentCard


router = APIRouter(
    prefix="/v1/platform-admin/modules/construction/agents",
    tags=["platform-admin", "construction-agents"],
)
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
OwnerDependency = Annotated[UserSession, Depends(require_owner)]
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]
PageLimit = Annotated[int, Query(ge=1, le=100)]

_AGENT_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_MODEL_PROFILE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,95}$")


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


class ConstructionAgentCardView(APIModel):
    agent_id: str = Field(alias="agentId")
    module_id: Literal["construction"] = Field(alias="moduleId")
    display_name: str = Field(alias="displayName")
    role: str
    system_prompt: str = Field(alias="systemPrompt")
    skills: list[str]
    capabilities: list[str]
    allowed_tools: list[str] = Field(alias="allowedTools")
    authority_limits: dict[str, object] = Field(alias="authorityLimits")
    forbidden_actions: list[str] = Field(alias="forbiddenActions")
    required_evidence: list[str] = Field(alias="requiredEvidence")
    handoff_rules: list[str] = Field(alias="handoffRules")
    completion_criteria: list[str] = Field(alias="completionCriteria")
    model_profile: str = Field(alias="modelProfile")
    card_version: str = Field(alias="cardVersion")
    configuration_revision: int = Field(alias="configurationRevision", ge=0)
    source: Literal["built_in", "configured"]
    updated_at: int | None = Field(default=None, alias="updatedAt")


class ConstructionAgentCardPage(APIModel):
    items: list[ConstructionAgentCardView]
    next_cursor: str | None = Field(default=None, alias="nextCursor")


class ConstructionAgentConfigurationPatch(APIModel):
    revision: Annotated[int, Field(ge=0)]
    system_prompt: Annotated[str, Field(min_length=20, max_length=32768)] | None = (
        Field(default=None, alias="systemPrompt")
    )
    model_profile: Annotated[str, Field(min_length=2, max_length=96)] | None = (
        Field(default=None, alias="modelProfile")
    )

    @model_validator(mode="after")
    def require_change(self) -> "ConstructionAgentConfigurationPatch":
        if not (self.model_fields_set - {"revision"}):
            raise ValueError("at least one agent configuration field is required")
        if (
            self.model_profile is not None
            and _MODEL_PROFILE.fullmatch(self.model_profile) is None
        ):
            raise ValueError("model profile is invalid")
        return self


def _configuration(
    database: sqlite3.Connection,
    *,
    agent_id: str,
) -> sqlite3.Row | None:
    return database.execute(
        """
        SELECT system_prompt, model_profile, revision, updated_at
        FROM construction_agent_configurations
        WHERE agent_id = ?
        LIMIT 1
        """,
        (agent_id,),
    ).fetchone()


def _project(
    card: ConstructionAgentCard,
    configuration: sqlite3.Row | None,
) -> ConstructionAgentCardView:
    configured = configuration is not None
    return ConstructionAgentCardView(
        agentId=card.agent_id,
        moduleId="construction",
        displayName=card.display_name,
        role=card.role,
        systemPrompt=(
            str(configuration["system_prompt"])
            if configured
            else card.system_prompt
        ),
        skills=list(card.skills),
        capabilities=list(card.capabilities),
        allowedTools=list(card.allowed_tools),
        authorityLimits=card.authority_limits,
        forbiddenActions=list(card.forbidden_actions),
        requiredEvidence=list(card.required_evidence),
        handoffRules=list(card.handoff_rules),
        completionCriteria=list(card.completion_criteria),
        modelProfile=(
            str(configuration["model_profile"])
            if configured
            else card.model_profile
        ),
        cardVersion=card.version,
        configurationRevision=(
            int(configuration["revision"])
            if configured
            else 0
        ),
        source="configured" if configured else "built_in",
        updatedAt=(
            int(configuration["updated_at"])
            if configured
            else None
        ),
    )


@router.get("", response_model=ConstructionAgentCardPage)
def list_construction_agents(
    database: DatabaseDependency,
    _owner: OwnerDependency,
    limit: PageLimit = 50,
    cursor: str | None = Query(default=None, max_length=128),
    q: str | None = Query(default=None, max_length=160),
) -> ConstructionAgentCardPage:
    if cursor is not None and _AGENT_ID.fullmatch(cursor) is None:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "construction_agent_cursor_invalid",
            "Agent cursor is invalid.",
        )
    query = (q or "").strip().casefold()
    cards = sorted(ALL_CONSTRUCTION_AGENTS.values(), key=lambda item: item.agent_id)
    if cursor is not None:
        cards = [card for card in cards if card.agent_id > cursor]
    if query:
        cards = [
            card
            for card in cards
            if query
            in f"{card.agent_id} {card.display_name} {card.role}".casefold()
        ]
    page = cards[: limit + 1]
    has_more = len(page) > limit
    page = page[:limit]
    items = [
        _project(card, _configuration(database, agent_id=card.agent_id))
        for card in page
    ]
    return ConstructionAgentCardPage(
        items=items,
        nextCursor=page[-1].agent_id if has_more and page else None,
    )


@router.patch("/{agent_id}", response_model=ConstructionAgentCardView)
def update_construction_agent(
    agent_id: str,
    payload: ConstructionAgentConfigurationPatch,
    database: DatabaseDependency,
    actor: OwnerDependency,
    _mutation_auth: MutationAuthDependency,
) -> ConstructionAgentCardView:
    if _AGENT_ID.fullmatch(agent_id) is None or agent_id not in ALL_CONSTRUCTION_AGENTS:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "construction_agent_not_found",
            "Construction agent was not found.",
        )
    card = ALL_CONSTRUCTION_AGENTS[agent_id]
    with transaction(database, immediate=True):
        current = _configuration(database, agent_id=agent_id)
        current_revision = 0 if current is None else int(current["revision"])
        if current_revision != payload.revision:
            raise _error(
                status.HTTP_409_CONFLICT,
                "construction_agent_revision_conflict",
                "Agent instructions changed; reload and try again.",
            )
        current_prompt = (
            card.system_prompt
            if current is None
            else str(current["system_prompt"])
        )
        current_model_profile = (
            card.model_profile
            if current is None
            else str(current["model_profile"])
        )
        system_prompt = (
            current_prompt
            if payload.system_prompt is None
            else payload.system_prompt.strip()
        )
        model_profile = (
            current_model_profile
            if payload.model_profile is None
            else payload.model_profile.strip()
        )
        if len(system_prompt) < 20 or _MODEL_PROFILE.fullmatch(model_profile) is None:
            raise _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "construction_agent_configuration_invalid",
                "Agent instructions or model profile are invalid.",
            )
        if system_prompt == current_prompt and model_profile == current_model_profile:
            raise _error(
                status.HTTP_409_CONFLICT,
                "construction_agent_configuration_unchanged",
                "Agent configuration has no changes.",
            )
        next_revision = current_revision + 1
        updated_at = int(time.time())
        database.execute(
            """
            INSERT INTO construction_agent_configurations (
                agent_id, system_prompt, model_profile, revision,
                updated_at, updated_by_user_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                system_prompt = excluded.system_prompt,
                model_profile = excluded.model_profile,
                revision = excluded.revision,
                updated_at = excluded.updated_at,
                updated_by_user_id = excluded.updated_by_user_id
            """,
            (
                agent_id,
                system_prompt,
                model_profile,
                next_revision,
                updated_at,
                actor.user_id,
            ),
        )
        database.execute(
            """
            INSERT INTO construction_agent_configuration_history (
                agent_id, revision, system_prompt, model_profile,
                created_at, created_by_user_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                next_revision,
                system_prompt,
                model_profile,
                updated_at,
                actor.user_id,
            ),
        )
    configuration = _configuration(database, agent_id=agent_id)
    if configuration is None:
        raise RuntimeError("construction agent configuration was not persisted")
    return _project(card, configuration)
