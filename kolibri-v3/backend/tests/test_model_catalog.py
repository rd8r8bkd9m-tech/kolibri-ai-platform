from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.agent_runtime import (
    AgentRuntimeCapabilities,
    AgentRuntimeDescriptor,
    AgentRuntimeRegistry,
    AgentRuntimeResult,
    DelegatingAgentRuntime,
)
from app.chat.models import AgUiRunInput
from app.codex_app_server import CodexModel
from app.model_catalog import (
    _load_snapshot,
    load_model_catalog,
    validate_model_selection,
)
from app.schemas import AgentProfile, AgentProfileUpdate


@dataclass(frozen=True, slots=True)
class AdvertisedModel:
    id: str
    display_name: str
    description: str
    supported_reasoning_efforts: tuple[tuple[str, str], ...] = ()
    default_reasoning_effort: str | None = None
    service_tiers: tuple[tuple[str, str, str], ...] = ()
    is_default: bool = False
    upgrade: str | None = None


class CatalogBackend:
    def __init__(
        self,
        models: tuple[object, ...],
        *,
        failure: Exception | None = None,
    ) -> None:
        self.models = models
        self.failure = failure

    def list_models(self, *, timeout: float) -> tuple[object, ...]:
        assert timeout == 10.0
        if self.failure is not None:
            raise self.failure
        return self.models


def _runtime(
    profile_id: str,
    display_name: str,
    *,
    backend: object | None,
    model_catalog: bool,
    priority: int,
) -> DelegatingAgentRuntime:
    return DelegatingAgentRuntime(
        descriptor=AgentRuntimeDescriptor(
            profile_id=profile_id,
            runtime_id=f"{profile_id}.runtime",
            display_name=display_name,
            auto_priority=priority,
            capabilities=AgentRuntimeCapabilities(
                modes=frozenset({"chat", "developer"}),
                streaming=True,
                structured_output=False,
                activity_events=True,
                persistent_sessions=True,
                model_catalog=model_catalog,
            ),
        ),
        execute=lambda _request: AgentRuntimeResult(text="unused"),
        model_catalog_backend=backend,
    )


def _request(registry: AgentRuntimeRegistry) -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(agent_runtime_registry=registry)
        )
    )


def _database(statuses: dict[str, str]) -> sqlite3.Connection:
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    database.execute(
        """
        CREATE TABLE provider_connections (
            tenant_id TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            status TEXT NOT NULL
        )
        """
    )
    database.executemany(
        """
        INSERT INTO provider_connections (tenant_id, provider_id, status)
        VALUES ('tenant_test', ?, ?)
        """,
        tuple(statuses.items()),
    )
    return database


def _gpt_5_6_models() -> tuple[CodexModel, ...]:
    return (
        CodexModel(
            id="gpt-5.6-sol",
            display_name="GPT-5.6 Sol",
            description="Frontier coding model.",
            supported_reasoning_efforts=(
                ("low", ""),
                ("medium", ""),
                ("high", ""),
                ("xhigh", ""),
                ("max", ""),
                ("ultra", ""),
            ),
            default_reasoning_effort="low",
            is_default=True,
            supports_personality=False,
            service_tiers=(),
            upgrade=None,
        ),
        CodexModel(
            id="gpt-5.6-terra",
            display_name="GPT-5.6 Terra",
            description="Balanced coding model.",
            supported_reasoning_efforts=(("low", ""), ("ultra", "")),
            default_reasoning_effort="low",
            is_default=False,
            supports_personality=False,
            service_tiers=(),
            upgrade=None,
        ),
        CodexModel(
            id="gpt-5.6-luna",
            display_name="GPT-5.6 Luna",
            description="Fast coding model.",
            supported_reasoning_efforts=(("low", ""), ("max", "")),
            default_reasoning_effort="low",
            is_default=False,
            supports_personality=False,
            service_tiers=(),
            upgrade=None,
        ),
    )


def test_profile_schemas_accept_bounded_runtime_ids_not_a_closed_enum() -> None:
    cached_ids = len(AgentProfile._value2member_map_)
    parsed = AgentProfileUpdate.model_validate({"profile": "acme-agent"})
    assert parsed.profile.value == "acme-agent"
    assert AgentProfile("acme-agent") == parsed.profile
    for index in range(1_000):
        assert AgentProfileUpdate.model_validate(
            {"profile": f"runtime-{index}"}
        ).profile.value == f"runtime-{index}"
    assert len(AgentProfile._value2member_map_) == cached_ids
    run = AgUiRunInput.model_validate(
        {
            "threadId": "thread_profile_schema_01",
            "runId": "run_profile_schema_01",
            "state": None,
            "messages": [
                {
                    "id": "message_profile_schema_01",
                    "role": "user",
                    "content": "Run the registered agent.",
                }
            ],
            "tools": [],
            "context": [],
            "forwardedProps": {
                "agentProfile": "acme-agent",
                "executionMode": "standard",
                "accessMode": "standard",
            },
        }
    )
    assert run.forwarded_props.agent_profile == "acme-agent"
    with pytest.raises(ValidationError):
        AgentProfileUpdate.model_validate({"profile": "Invalid Profile"})


def test_catalog_is_supplied_by_registered_runtime_descriptors() -> None:
    registry = AgentRuntimeRegistry()
    registry.register(
        _runtime(
            "codex-cli",
            "Codex CLI",
            backend=CatalogBackend(_gpt_5_6_models()),
            model_catalog=True,
            priority=20,
        )
    )
    registry.register(
        _runtime(
            "mimo-code",
            "MiMo Code",
            backend=None,
            model_catalog=False,
            priority=10,
        )
    )
    database = _database(
        {"codex-cli": "connected", "mimo-code": "connected"}
    )
    try:
        entries, legacy_codex_available = load_model_catalog(
            _request(registry),
            database,
            tenant_id="tenant_test",
        )
    finally:
        database.close()

    assert legacy_codex_available is True
    assert [entry.id for entry in entries] == [
        "auto",
        "mimo-code",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
    ]
    assert [entry.display_name for entry in entries[2:]] == [
        "GPT-5.6 Sol",
        "GPT-5.6 Terra",
        "GPT-5.6 Luna",
    ]
    assert entries[1].profile is AgentProfile.MIMO_CODE
    assert entries[1].is_default is True
    assert all(entry.available for entry in entries)


def test_fake_third_runtime_is_visible_and_selectable_without_catalog_branch() -> None:
    registry = AgentRuntimeRegistry()
    registry.register(
        _runtime(
            "acme-agent",
            "Acme Agent",
            backend=CatalogBackend(
                (
                    AdvertisedModel(
                        id="acme-reasoner",
                        display_name="Acme Reasoner",
                        description="Third-party registered model.",
                        supported_reasoning_efforts=(("high", "Thorough"),),
                        default_reasoning_effort="high",
                        service_tiers=(
                            ("priority", "Fast", "Higher throughput"),
                        ),
                        is_default=True,
                    ),
                )
            ),
            model_catalog=True,
            priority=30,
        )
    )
    request = _request(registry)
    database = _database({"acme-agent": "connected"})
    try:
        snapshot = _load_snapshot(
            request,
            database,
            tenant_id="tenant_test",
        )
        selected = validate_model_selection(
            request,
            database,
            tenant_id="tenant_test",
            profile=AgentProfile("acme-agent"),
            model="acme-reasoner",
            reasoning_effort="high",
            service_tier="priority",
        )
    finally:
        database.close()

    assert [profile.id.value for profile in snapshot.profiles] == ["acme-agent"]
    assert snapshot.profiles[0].model_catalog_available is True
    assert snapshot.models[-1].profile.value == "acme-agent"
    assert selected.id == "acme-reasoner"


def test_catalog_failure_and_unknown_profile_fail_closed_without_substitution() -> None:
    registry = AgentRuntimeRegistry()
    registry.register(
        _runtime(
            "broken-agent",
            "Broken Agent",
            backend=CatalogBackend((), failure=RuntimeError("offline")),
            model_catalog=True,
            priority=10,
        )
    )
    request = _request(registry)
    database = _database({"broken-agent": "connected"})
    try:
        with pytest.raises(HTTPException) as unavailable:
            validate_model_selection(
                request,
                database,
                tenant_id="tenant_test",
                profile=AgentProfile("broken-agent"),
                model="some-model",
                reasoning_effort=None,
            )
        with pytest.raises(HTTPException) as unknown:
            validate_model_selection(
                request,
                database,
                tenant_id="tenant_test",
                profile=AgentProfile("unknown-agent"),
                model="some-model",
                reasoning_effort=None,
            )
    finally:
        database.close()

    assert unavailable.value.status_code == 503
    assert unavailable.value.detail["code"] == "model_catalog_unavailable"
    assert unknown.value.status_code == 422
    assert unknown.value.detail["code"] == "agent_profile_not_registered"


def test_runtime_model_availability_and_options_are_validated_exactly() -> None:
    registry = AgentRuntimeRegistry()
    registry.register(
        _runtime(
            "tiered-agent",
            "Tiered Agent",
            backend=CatalogBackend(
                (
                    AdvertisedModel(
                        id="tiered-model",
                        display_name="Tiered Model",
                        description="Runtime-owned tiered model.",
                        supported_reasoning_efforts=(("high", "Thorough"),),
                        default_reasoning_effort="high",
                        service_tiers=(("priority", "Fast", "Higher speed"),),
                        is_default=True,
                    ),
                )
            ),
            model_catalog=True,
            priority=10,
        )
    )
    request = _request(registry)
    disconnected = _database({"tiered-agent": "not_configured"})
    try:
        with pytest.raises(HTTPException) as connection_error:
            validate_model_selection(
                request,
                disconnected,
                tenant_id="tenant_test",
                profile=AgentProfile("tiered-agent"),
                model="tiered-model",
                reasoning_effort="high",
                service_tier="priority",
            )
    finally:
        disconnected.close()
    assert connection_error.value.status_code == 409

    connected = _database({"tiered-agent": "connected"})
    try:
        with pytest.raises(HTTPException) as effort_error:
            validate_model_selection(
                request,
                connected,
                tenant_id="tenant_test",
                profile=AgentProfile("tiered-agent"),
                model="tiered-model",
                reasoning_effort="ultra",
                service_tier="priority",
            )
        with pytest.raises(HTTPException) as tier_error:
            validate_model_selection(
                request,
                connected,
                tenant_id="tenant_test",
                profile=AgentProfile("tiered-agent"),
                model="tiered-model",
                reasoning_effort="high",
                service_tier="burst",
            )
    finally:
        connected.close()

    assert effort_error.value.detail["code"] == (
        "reasoning_effort_not_supported"
    )
    assert tier_error.value.detail["code"] == "service_tier_not_supported"
