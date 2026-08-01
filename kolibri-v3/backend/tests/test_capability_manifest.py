from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from types import SimpleNamespace

from app.agent_runtime import (
    AgentRuntimeCapabilities,
    AgentRuntimeDescriptor,
    AgentRuntimeRegistry,
    DelegatingAgentRuntime,
    LIVE_WEB_SEARCH_CAPABILITY_ID,
)
from app.capability_manifest import build_capability_manifest
from app.image_generation import IMAGE_GENERATION_CAPABILITY_ID
from app.schemas import AgentProfile, UserRole, UserSession


@dataclass
class _AppState:
    agent_runtime_registry: AgentRuntimeRegistry


def _identity() -> UserSession:
    return UserSession(
        user_id="user-capability-test",
        tenant_id="tenant-capability-test",
        role=UserRole.OWNER,
        preferred_agent_profile=AgentProfile.AUTO,
        email="owner@example.test",
        name="Owner",
        is_platform_owner=True,
        product_capabilities=("construction.estimates.workspace",),
    )


def test_capability_manifest_is_server_truth_for_connected_runtime(
    tmp_path,
) -> None:
    del tmp_path
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    database.execute(
        "CREATE TABLE provider_connections (tenant_id TEXT, provider_id TEXT, status TEXT)"
    )
    database.execute(
        "INSERT INTO provider_connections VALUES (?, ?, ?)",
        ("tenant-capability-test", "mimo-code", "connected"),
    )
    registry = AgentRuntimeRegistry()
    registry.register(
        DelegatingAgentRuntime(
            descriptor=AgentRuntimeDescriptor(
                profile_id="mimo-code",
                runtime_id="mimo-code-runtime",
                display_name="MiMo Code",
                capabilities=AgentRuntimeCapabilities(
                    modes=frozenset({"chat", "developer"}),
                    streaming=True,
                    structured_output=False,
                    activity_events=True,
                    persistent_sessions=True,
                    capability_ids=frozenset({LIVE_WEB_SEARCH_CAPABILITY_ID}),
                ),
            ),
            execute=lambda _request: None,  # type: ignore[arg-type]
        )
    )
    registry.register_capability(
        IMAGE_GENERATION_CAPABILITY_ID,
        object(),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=_AppState(registry)))

    manifest = build_capability_manifest(request, database, _identity())
    capabilities = {item["id"]: item for item in manifest["capabilities"]}
    assert capabilities[LIVE_WEB_SEARCH_CAPABILITY_ID]["available"] is True
    assert capabilities["weather.current"]["available"] is True
    assert capabilities["files.attach"]["available"] is True
    assert capabilities["construction.estimates.workspace"]["available"] is True
    assert capabilities["developer.runtime.execute"]["available"] is True
    assert capabilities[IMAGE_GENERATION_CAPABILITY_ID]["available"] is False
    assert manifest["runtimes"][0]["connected"] is True

    database.close()
