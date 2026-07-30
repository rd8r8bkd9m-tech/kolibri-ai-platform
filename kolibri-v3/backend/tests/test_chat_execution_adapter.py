from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
import pytest

import app.chat.execution_adapter as execution_adapter
from app.chat.models import AgUiRunInput
from app.chat.service import accept_run
from app.config import Settings
from app.database import connect_database
from app.main import create_app
from app.owner_bootstrap import promote_registered_owner
from app.schemas import AgentProfile, UserRole, UserSession


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"


def _run_input(
    *,
    mode: str,
    profile: str,
    content: str = "Проверь контур выполнения.",
) -> AgUiRunInput:
    return AgUiRunInput.model_validate(
        {
            "threadId": f"thread_plane_{mode}_01",
            "runId": f"run_plane_{mode}_01",
            "state": None,
            "messages": [
                {
                    "id": f"message_plane_{mode}_01",
                    "role": "user",
                    "content": content,
                }
            ],
            "tools": [],
            "context": [],
            "forwardedProps": {
                "agentProfile": profile,
                "executionMode": mode,
                "accessMode": "auto" if mode == "developer" else "standard",
            },
        }
    )


def _owner(database_path: Path) -> tuple[Settings, UserSession, Request]:
    settings = Settings.for_testing(database_url=database_path)
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post(
            "/v1/auth/register",
            headers=ORIGIN,
            json={
                "email": "owner@example.com",
                "name": "Owner",
                "password": PASSWORD,
            },
        )
        assert response.status_code == 201
        user = response.json()["user"]
        promote_registered_owner(settings, email="owner@example.com")
    identity = UserSession(
        user_id=user["id"],
        tenant_id=user["tenantId"],
        role=UserRole.OWNER,
        preferred_agent_profile=AgentProfile.AUTO,
        email=user["email"],
        name=user["name"],
        is_platform_owner=True,
        platform_capabilities=(
            "platform.admin",
            "chat.developer.request",
            "chat.use",
        ),
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/ag-ui",
            "headers": [],
            "app": app,
        }
    )
    return settings, identity, request


def _production(base: Settings, *, direct: bool) -> Settings:
    return replace(
        base,
        environment="production",
        allowed_origins=("https://app.example.test",),
        cookie_secure=True,
        direct_model_runtime_enabled=direct,
        developer_agent_enabled=False,
        developer_workspace_root=None,
    )


def test_production_routes_standard_direct_and_developer_external_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, identity, request = _owner(tmp_path / "direct-plane.db")
    settings = _production(base, direct=True)
    monkeypatch.setattr(
        execution_adapter,
        "validate_profile_selection",
        lambda _request, _database, *, tenant_id, profile: (
            None
            if profile == AgentProfile.AUTO
            else SimpleNamespace(
                modes=("developer",),
                model_selection_supported=False,
            )
        ),
    )
    database = connect_database(settings.database_url)
    try:
        standard = execution_adapter.prepare_chat_execution(
            request,
            database,
            settings=settings,
            identity=identity,
            run_input=_run_input(mode="standard", profile="auto"),
        )
        assert standard.execution_plane == "direct"

        without_capability = replace(
            identity,
            platform_capabilities=("platform.admin", "chat.use"),
        )
        with pytest.raises(HTTPException) as denied:
            execution_adapter.prepare_chat_execution(
                request,
                database,
                settings=settings,
                identity=without_capability,
                run_input=_run_input(
                    mode="developer",
                    profile="mimo-code",
                ),
            )
        assert denied.value.status_code == 403
        assert denied.value.detail["code"] == "owner_required"

        developer_input = _run_input(
            mode="developer",
            profile="mimo-code",
        )
        developer = execution_adapter.prepare_chat_execution(
            request,
            database,
            settings=settings,
            identity=identity,
            run_input=developer_input,
        )
        assert developer.execution_plane == "home"
        accepted = accept_run(
            database,
            settings=settings,
            identity=identity,
            run_input=developer_input,
            prepared=developer,
        )
        assert accepted.execution_plane == "home"
        assert database.execute(
            """
            SELECT COUNT(*)
            FROM product_run_outbox
            WHERE tenant_id = ? AND run_id = ?
            """,
            (identity.tenant_id, accepted.run_id),
        ).fetchone()[0] == 1
    finally:
        database.close()


def test_browser_cannot_supply_an_execution_plane() -> None:
    payload = _run_input(
        mode="developer",
        profile="mimo-code",
    ).model_dump(mode="json", by_alias=True)
    payload["forwardedProps"]["executionPlane"] = "direct"

    with pytest.raises(ValueError):
        AgUiRunInput.model_validate(payload)


def test_standard_product_mode_uses_chat_runtime_capability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, identity, request = _owner(tmp_path / "standard-chat-mode.db")
    settings = replace(settings, direct_model_runtime_enabled=True)
    monkeypatch.setattr(
        execution_adapter,
        "validate_profile_selection",
        lambda _request, _database, *, tenant_id, profile: SimpleNamespace(
            modes=("chat",),
            model_selection_supported=False,
        ),
    )

    database = connect_database(settings.database_url)
    try:
        prepared = execution_adapter.prepare_chat_execution(
            request,
            database,
            settings=settings,
            identity=identity,
            run_input=_run_input(
                mode="standard",
                profile="codex-cli",
            ),
        )
    finally:
        database.close()

    assert prepared.execution_plane == "direct"
    assert prepared.runtime_profile == "codex-cli"


def test_estimate_product_mode_uses_structured_runtime_capability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, identity, request = _owner(tmp_path / "structured-mode.db")
    settings = replace(settings, direct_model_runtime_enabled=True)
    monkeypatch.setattr(
        execution_adapter,
        "validate_profile_selection",
        lambda _request, _database, *, tenant_id, profile: SimpleNamespace(
            modes=("structured",),
            model_selection_supported=False,
        ),
    )

    database = connect_database(settings.database_url)
    try:
        prepared = execution_adapter.prepare_chat_execution(
            request,
            database,
            settings=settings,
            identity=identity,
            run_input=_run_input(
                mode="standard",
                profile="codex-cli",
                content="Составь смету на штукатурку стен площадью 100 м².",
            ),
        )
    finally:
        database.close()

    assert prepared.execution_plane == "direct"
    assert prepared.runtime_profile == "codex-cli"


def test_production_home_plane_routes_standard_and_developer_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, identity, request = _owner(tmp_path / "home-plane.db")
    settings = _production(base, direct=False)
    monkeypatch.setattr(
        execution_adapter,
        "validate_profile_selection",
        lambda _request, _database, *, tenant_id, profile: (
            None
            if profile == AgentProfile.AUTO
            else SimpleNamespace(
                modes=("developer",),
                model_selection_supported=False,
            )
        ),
    )
    database = connect_database(settings.database_url)
    try:
        standard = execution_adapter.prepare_chat_execution(
            request,
            database,
            settings=settings,
            identity=identity,
            run_input=_run_input(mode="standard", profile="auto"),
        )
        developer = execution_adapter.prepare_chat_execution(
            request,
            database,
            settings=settings,
            identity=identity,
            run_input=_run_input(
                mode="developer",
                profile="mimo-code",
            ),
        )
        assert standard.execution_plane == "home"
        assert developer.execution_plane == "home"
        assert developer.runtime_profile == "mimo-code"
        assert developer.model_id is None
    finally:
        database.close()
