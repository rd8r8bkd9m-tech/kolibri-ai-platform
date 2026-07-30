from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent_runtime import (
    AgentRuntimeCapabilities,
    AgentRuntimeDescriptor,
    AgentRuntimeRegistry,
    AgentRuntimeResult,
    DelegatingAgentRuntime,
)
from app.codex_app_server import CodexModel
from app.config import Settings
from app.database import migration_paths
from app.direct_model_runtime import DirectModelError, _finish_error
from app.main import create_app
from app.owner_bootstrap import OwnerBootstrapError, promote_registered_owner


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
LATEST_SCHEMA_VERSION = int(migration_paths()[-1].name.split("_", 1)[0])


def _settings(database_path: Path) -> Settings:
    return Settings.for_testing(
        database_url=database_path,
        bootstrap_owner_email="owner@example.com",
    )


def _register(
    client: TestClient,
    *,
    email: str,
    name: str = "Kolibri User",
):
    return client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={"email": email, "name": name, "password": PASSWORD},
    )


def _catalog_registry(
    codex_backend: object,
    *,
    extra_runtimes: tuple[DelegatingAgentRuntime, ...] = (),
) -> AgentRuntimeRegistry:
    registry = AgentRuntimeRegistry()
    registry.register(
        DelegatingAgentRuntime(
            descriptor=AgentRuntimeDescriptor(
                profile_id="codex-cli",
                runtime_id="codex-cli.runtime",
                display_name="Codex CLI",
                auto_priority=20,
                capabilities=AgentRuntimeCapabilities(
                    modes=frozenset({"chat", "developer"}),
                    streaming=True,
                    structured_output=False,
                    activity_events=True,
                    persistent_sessions=True,
                    model_catalog=True,
                ),
            ),
            execute=lambda _request: AgentRuntimeResult(text="unused"),
            model_catalog_backend=codex_backend,
        )
    )
    registry.register(
        DelegatingAgentRuntime(
            descriptor=AgentRuntimeDescriptor(
                profile_id="mimo-code",
                runtime_id="mimo-code.runtime",
                display_name="MiMo Code",
                auto_priority=10,
                capabilities=AgentRuntimeCapabilities(
                    modes=frozenset({"chat", "developer"}),
                    streaming=True,
                    structured_output=False,
                    activity_events=True,
                    persistent_sessions=True,
                    model_catalog=False,
                ),
            ),
            execute=lambda _request: AgentRuntimeResult(text="unused"),
        )
    )
    for runtime in extra_runtimes:
        registry.register(runtime)
    return registry


def _configure_owner_codex_selection(
    client: TestClient,
    *,
    database_path: Path,
    tenant_id: str,
    csrf: str,
) -> None:
    class Runtime:
        def list_models(self, *, timeout: float) -> tuple[CodexModel, ...]:
            assert timeout == 10.0
            return (
                CodexModel(
                    id="gpt-owner-explicit",
                    display_name="Owner Explicit",
                    description="Test-only explicit developer model.",
                    supported_reasoning_efforts=(("high", "Thorough"),),
                    default_reasoning_effort="high",
                    is_default=True,
                    supports_personality=False,
                    service_tiers=(),
                    upgrade=None,
                ),
            )

    database = sqlite3.connect(database_path)
    try:
        database.execute(
            """
            INSERT INTO provider_connections (
                tenant_id, provider_id, status, authority_observed,
                last_verified_at, created_at, updated_at
            ) VALUES (?, 'codex-cli', 'connected', 1, 'now', 'now', 'now')
            ON CONFLICT(tenant_id, provider_id) DO UPDATE SET
                status = 'connected',
                authority_observed = 1,
                updated_at = 'now'
            """,
            (tenant_id,),
        )
        database.commit()
    finally:
        database.close()
    client.app.state.agent_runtime_registry = _catalog_registry(Runtime())
    selected = client.put(
        "/v1/profile/model-settings",
        headers={**ORIGIN, "X-CSRF-Token": csrf},
        json={
            "profile": "codex-cli",
            "model": "gpt-owner-explicit",
            "reasoningEffort": "high",
        },
    )
    assert selected.status_code == 200


def test_registration_session_profile_and_logout_are_durable(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "identity.db"
    with TestClient(create_app(_settings(database_path))) as client:
        registered = _register(
            client,
            email="owner@example.com",
            name="Owner",
        )
        assert registered.status_code == 201
        assert registered.json()["user"]["role"] == "user"
        assert registered.json()["user"]["preferredAgentProfile"] == "auto"
        assert client.cookies.get("kolibri_v3_session")
        csrf = client.cookies.get("kolibri_v3_csrf")
        assert csrf

        session = client.get("/v1/session")
        assert session.status_code == 200
        assert session.json()["authenticated"] is True
        assert session.headers["cache-control"] == "no-store"

        updated = client.patch(
            "/v1/profile",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={"name": "Owner Updated"},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Owner Updated"

        database = sqlite3.connect(database_path)
        try:
            database.execute(
                """
                INSERT INTO provider_connections (
                    tenant_id, provider_id, status, authority_observed,
                    last_verified_at, created_at, updated_at
                ) VALUES (?, 'mimo-code', 'connected', 1, 'now', 'now', 'now')
                """,
                (registered.json()["user"]["tenantId"],),
            )
            database.commit()
        finally:
            database.close()
        client.app.state.agent_runtime_registry = _catalog_registry(object())
        selected = client.put(
            "/v1/profile/agent-profile",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={"profile": "mimo-code"},
        )
        assert selected.status_code == 200
        assert selected.json()["preferredAgentProfile"] == "mimo-code"

        logged_out = client.post(
            "/v1/auth/logout",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
        )
        assert logged_out.status_code == 200
        assert logged_out.json() == {"authenticated": False, "user": None}
        assert client.get("/v1/session").json()["authenticated"] is False

    database = sqlite3.connect(database_path)
    try:
        password_hash = database.execute(
            "SELECT password_hash FROM users WHERE email_normalized = ?",
            ("owner@example.com",),
        ).fetchone()[0]
        assert PASSWORD not in password_hash
        assert password_hash.startswith("scrypt-v1$")
        assert (
            database.execute("PRAGMA user_version").fetchone()[0]
            == LATEST_SCHEMA_VERSION
        )
        assert database.execute(
            "SELECT COUNT(*) FROM identity_events"
        ).fetchone()[0] >= 4
    finally:
        database.close()


def test_profile_only_endpoints_reject_unregistered_runtime_without_writes(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "unregistered-runtime.db"
    with TestClient(create_app(_settings(database_path))) as client:
        registered = _register(client, email="registry@example.com")
        assert registered.status_code == 201
        csrf = str(client.cookies.get("kolibri_v3_csrf"))
        client.app.state.agent_runtime_registry = _catalog_registry(object())
        database = sqlite3.connect(database_path)
        try:
            event_count = database.execute(
                "SELECT COUNT(*) FROM identity_events"
            ).fetchone()[0]
        finally:
            database.close()

        for method, path, payload in (
            (
                client.put,
                "/v1/profile/agent-profile",
                {"profile": "unknown-agent"},
            ),
            (
                client.patch,
                "/v1/profile",
                {"preferredAgentProfile": "unknown-agent"},
            ),
        ):
            rejected = method(
                path,
                headers={**ORIGIN, "X-CSRF-Token": csrf},
                json=payload,
            )
            assert rejected.status_code == 422
            assert rejected.json()["code"] == "agent_profile_not_registered"
            assert (
                client.get("/v1/profile").json()["preferredAgentProfile"]
                == "auto"
            )

        database = sqlite3.connect(database_path)
        try:
            assert database.execute(
                "SELECT preferred_agent_profile FROM users"
            ).fetchone()[0] == "auto"
            assert database.execute(
                "SELECT COUNT(*) FROM identity_events"
            ).fetchone()[0] == event_count
        finally:
            database.close()


def test_model_service_tier_is_validated_persisted_and_returned(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "model-service-tier.db"
    settings = _settings(database_path)

    class Runtime:
        configured_model = "gpt-tiered"
        configured_effort = "high"

        def list_models(self, *, timeout: float) -> tuple[CodexModel, ...]:
            assert timeout == 10.0
            return (
                CodexModel(
                    id="gpt-tiered",
                    display_name="GPT Tiered",
                    description="Test model with a real service tier.",
                    supported_reasoning_efforts=(("high", "Thorough"),),
                    default_reasoning_effort="high",
                    is_default=True,
                    supports_personality=False,
                    service_tiers=(
                        (
                            "priority",
                            "Fast",
                            "1.5x speed, increased usage",
                        ),
                    ),
                    upgrade=None,
                ),
            )

    with TestClient(create_app(settings)) as client:
        registered = _register(
            client,
            email="tiered@example.com",
            name="Tiered",
        )
        assert registered.status_code == 201
        user = registered.json()["user"]
        csrf = client.cookies.get("kolibri_v3_csrf")
        assert csrf
        database = sqlite3.connect(database_path)
        try:
            database.executemany(
                """
                INSERT INTO provider_connections (
                    tenant_id, provider_id, status, auth_flow_supported,
                    authority_observed, last_verified_at, created_at, updated_at
                ) VALUES (?, ?, 'connected', 0, 1, ?, ?, ?)
                """,
                [
                    (
                        user["tenantId"],
                        provider_id,
                        "2026-07-29T00:00:00Z",
                        "2026-07-29T00:00:00Z",
                        "2026-07-29T00:00:00Z",
                    )
                    for provider_id in ("codex-cli", "mimo-code")
                ],
            )
            database.commit()
        finally:
            database.close()
        client.app.state.agent_runtime_registry = _catalog_registry(Runtime())

        selected = client.put(
            "/v1/profile/model-settings",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={
                "profile": "codex-cli",
                "model": "gpt-tiered",
                "reasoningEffort": "high",
                "serviceTier": "priority",
            },
        )
        assert selected.status_code == 200
        assert selected.json()["preferredModelProfile"] == "codex-cli"
        assert selected.json()["preferredServiceTier"] == "priority"
        database = sqlite3.connect(database_path)
        try:
            event_count = database.execute(
                """
                SELECT COUNT(*)
                FROM identity_events
                WHERE event_type = 'profile_updated'
                """
            ).fetchone()[0]
        finally:
            database.close()
        replayed = client.put(
            "/v1/profile/model-settings",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={
                "profile": "codex-cli",
                "model": "gpt-tiered",
                "reasoningEffort": "high",
                "serviceTier": "priority",
            },
        )
        assert replayed.status_code == 200
        database = sqlite3.connect(database_path)
        try:
            assert database.execute(
                """
                SELECT COUNT(*)
                FROM identity_events
                WHERE event_type = 'profile_updated'
                """
            ).fetchone()[0] == event_count
        finally:
            database.close()
        assert (
            client.get("/v1/session").json()["user"][
                "preferredServiceTier"
            ]
            == "priority"
        )
        assert (
            client.get("/v1/profile").json()["preferredServiceTier"]
            == "priority"
        )

        routed_to_mimo = client.put(
            "/v1/profile/model-settings",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={
                "profile": "mimo-code",
                "model": "mimo-code",
                "reasoningEffort": None,
                "serviceTier": None,
            },
        )
        assert routed_to_mimo.status_code == 200
        assert routed_to_mimo.json()["preferredAgentProfile"] == "mimo-code"
        assert routed_to_mimo.json()["preferredModelProfile"] is None
        assert routed_to_mimo.json()["preferredModel"] is None
        assert routed_to_mimo.json()["preferredReasoningEffort"] is None
        assert routed_to_mimo.json()["preferredServiceTier"] is None

        restored = client.put(
            "/v1/profile/agent-profile",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={"profile": "codex-cli"},
        )
        assert restored.status_code == 200
        assert restored.json()["preferredModelProfile"] == "codex-cli"
        assert restored.json()["preferredModel"] == "gpt-tiered"
        assert restored.json()["preferredReasoningEffort"] == "high"
        assert restored.json()["preferredServiceTier"] == "priority"

        rejected = client.put(
            "/v1/profile/model-settings",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={
                "profile": "codex-cli",
                "model": "gpt-tiered",
                "reasoningEffort": "high",
                "serviceTier": "burst",
            },
        )
        assert rejected.status_code == 422
        assert rejected.json()["code"] == (
            "service_tier_not_supported"
        )
        assert (
            client.get("/v1/profile").json()["preferredServiceTier"]
            == "priority"
        )

        standard = client.put(
            "/v1/profile/model-settings",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={
                "profile": "codex-cli",
                "model": "gpt-tiered",
                "reasoningEffort": "high",
                "serviceTier": None,
            },
        )
        assert standard.status_code == 200
        assert standard.json()["preferredServiceTier"] is None

    database = sqlite3.connect(database_path)
    try:
        assert database.execute(
            """
            SELECT runtime_profile, model_id, reasoning_effort, service_tier
            FROM user_model_preferences
            """
        ).fetchall() == [("codex-cli", "gpt-tiered", "high", None)]
    finally:
        database.close()


def test_fake_runtime_preferences_are_isolated_per_profile(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "profile-preferences.db"
    settings = _settings(database_path)

    class Backend:
        def __init__(self, model: CodexModel) -> None:
            self.model = model

        def list_models(self, *, timeout: float) -> tuple[CodexModel, ...]:
            assert timeout == 10.0
            return (self.model,)

    codex_backend = Backend(
        CodexModel(
            id="gpt-codex-saved",
            display_name="Codex Saved",
            description="Codex preference.",
            supported_reasoning_efforts=(("high", ""),),
            default_reasoning_effort="high",
            is_default=True,
            supports_personality=False,
            service_tiers=(),
            upgrade=None,
        )
    )
    acme_backend = Backend(
        CodexModel(
            id="acme-saved",
            display_name="Acme Saved",
            description="Third runtime preference.",
            supported_reasoning_efforts=(("medium", ""),),
            default_reasoning_effort="medium",
            is_default=True,
            supports_personality=False,
            service_tiers=(),
            upgrade=None,
        )
    )
    acme_runtime = DelegatingAgentRuntime(
        descriptor=AgentRuntimeDescriptor(
            profile_id="acme-agent",
            runtime_id="acme-agent.runtime",
            display_name="Acme Agent",
            auto_priority=30,
            capabilities=AgentRuntimeCapabilities(
                modes=frozenset({"chat"}),
                streaming=True,
                structured_output=False,
                activity_events=False,
                persistent_sessions=True,
                model_catalog=True,
            ),
        ),
        execute=lambda _request: AgentRuntimeResult(text="unused"),
        model_catalog_backend=acme_backend,
    )

    with TestClient(create_app(settings)) as client:
        registered = _register(client, email="profiles@example.com")
        assert registered.status_code == 201
        user = registered.json()["user"]
        csrf = str(client.cookies.get("kolibri_v3_csrf"))
        database = sqlite3.connect(database_path)
        try:
            database.executemany(
                """
                INSERT INTO provider_connections (
                    tenant_id, provider_id, status, authority_observed,
                    last_verified_at, created_at, updated_at
                ) VALUES (?, ?, 'connected', 1, 'now', 'now', 'now')
                """,
                (
                    (user["tenantId"], "codex-cli"),
                    (user["tenantId"], "acme-agent"),
                ),
            )
            database.commit()
        finally:
            database.close()
        client.app.state.agent_runtime_registry = _catalog_registry(
            codex_backend,
            extra_runtimes=(acme_runtime,),
        )

        codex = client.put(
            "/v1/profile/model-settings",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={
                "profile": "codex-cli",
                "model": "gpt-codex-saved",
                "reasoningEffort": "high",
                "serviceTier": None,
            },
        )
        assert codex.status_code == 200
        assert codex.json()["preferredModelProfile"] == "codex-cli"

        acme = client.put(
            "/v1/profile/model-settings",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={
                "profile": "acme-agent",
                "model": "acme-saved",
                "reasoningEffort": "medium",
                "serviceTier": None,
            },
        )
        assert acme.status_code == 200
        assert acme.json()["preferredAgentProfile"] == "acme-agent"
        assert acme.json()["preferredModelProfile"] == "acme-agent"
        assert acme.json()["preferredModel"] == "acme-saved"

        codex_backend.model = CodexModel(
            id="gpt-codex-replacement",
            display_name="Codex Replacement",
            description="Current catalog no longer advertises the saved model.",
            supported_reasoning_efforts=(("high", ""),),
            default_reasoning_effort="high",
            is_default=True,
            supports_personality=False,
            service_tiers=(),
            upgrade=None,
        )
        stale = client.put(
            "/v1/profile/agent-profile",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={"profile": "codex-cli"},
        )
        assert stale.status_code == 422
        assert stale.json()["code"] == "model_not_supported"
        assert (
            client.get("/v1/profile").json()["preferredAgentProfile"]
            == "acme-agent"
        )
        codex_backend.model = CodexModel(
            id="gpt-codex-saved",
            display_name="Codex Saved",
            description="Codex preference.",
            supported_reasoning_efforts=(("high", ""),),
            default_reasoning_effort="high",
            is_default=True,
            supports_personality=False,
            service_tiers=(),
            upgrade=None,
        )
        restored = client.put(
            "/v1/profile/agent-profile",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={"profile": "codex-cli"},
        )
        assert restored.status_code == 200
        assert restored.json()["preferredModelProfile"] == "codex-cli"
        assert restored.json()["preferredModel"] == "gpt-codex-saved"

        automatic = client.put(
            "/v1/profile/model-settings",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={
                "profile": "auto",
                "model": "auto",
                "reasoningEffort": None,
                "serviceTier": None,
            },
        )
        assert automatic.status_code == 200
        assert automatic.json()["preferredAgentProfile"] == "auto"
        assert automatic.json()["preferredModelProfile"] is None
        assert automatic.json()["preferredModel"] is None

    database = sqlite3.connect(database_path)
    try:
        assert database.execute(
            """
            SELECT runtime_profile, model_id, reasoning_effort
            FROM user_model_preferences
            ORDER BY runtime_profile
            """
        ).fetchall() == [
            ("acme-agent", "acme-saved", "medium"),
            ("codex-cli", "gpt-codex-saved", "high"),
        ]
    finally:
        database.close()


def test_public_registration_never_grants_owner_authority(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "tenants.db")
    with TestClient(create_app(settings)) as client:
        regular = _register(client, email="person@example.com", name="Person")
        assert regular.status_code == 201
        assert regular.json()["user"]["role"] == "user"

        owner = _register(client, email="owner@example.com", name="Owner")
        assert owner.status_code == 201
        assert owner.json()["user"]["role"] == "user"
        assert (
            owner.json()["user"]["tenantId"]
            != regular.json()["user"]["tenantId"]
        )

        promoted = promote_registered_owner(
            settings,
            email="owner@example.com",
        )
        assert promoted.changed is True
        assert client.get("/v1/session").json()["user"]["role"] == "owner"
        assert (
            promote_registered_owner(
                settings,
                email="owner@example.com",
            ).changed
            is False
        )
        try:
            promote_registered_owner(settings, email="person@example.com")
        except OwnerBootstrapError:
            pass
        else:
            raise AssertionError("bootstrap email constraint was bypassed")


def test_developer_agent_mode_is_owner_only_and_audited(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "developer-agent.db"
    settings = replace(
        _settings(database_path),
        direct_model_runtime_enabled=True,
        developer_agent_enabled=True,
        developer_workspace_root=tmp_path,
    )

    def terminal_execute(
        run_settings,
        accepted,
        _runtime_registry,
        *,
        cancellation_signal=None,
    ):
        del cancellation_signal
        _finish_error(
            run_settings,
            accepted,
            DirectModelError("test_complete", "Test completed."),
        )

    monkeypatch.setattr(
        "app.chat.execution_adapter.execute_direct_run",
        terminal_execute,
    )

    with TestClient(create_app(settings)) as client:
        registered = _register(
            client,
            email="owner@example.com",
            name="Owner",
        )
        assert registered.status_code == 201
        csrf = client.cookies.get("kolibri_v3_csrf")
        assert csrf
        payload = json.loads(
            (
                Path(__file__).parents[2]
                / "contracts/v1/chat/examples/valid-ag-ui-run-input.json"
            ).read_text(encoding="utf-8")
        )
        payload["forwardedProps"]["executionMode"] = "developer"
        payload["forwardedProps"]["accessMode"] = "full"

        denied = client.post(
            "/v1/chat/ag-ui",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json=payload,
        )
        assert denied.status_code == 403
        assert denied.json()["code"] == "owner_required"

        promotion = promote_registered_owner(
            settings,
            email="owner@example.com",
        )
        assert promotion.changed is True
        _configure_owner_codex_selection(
            client,
            database_path=database_path,
            tenant_id=registered.json()["user"]["tenantId"],
            csrf=str(csrf),
        )
        payload["forwardedProps"]["agentProfile"] = "codex-cli"

        accepted = client.post(
            "/v1/chat/ag-ui",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json=payload,
        )
        assert accepted.status_code == 200
        assert '"type":"RUN_STARTED"' in accepted.text
        assert '"type":"RUN_ERROR"' in accepted.text

    database = sqlite3.connect(database_path)
    try:
        row = database.execute(
            """
            SELECT execution_mode, access_mode, authority_role, workspace_ref,
                   sandbox_profile, approval_policy, approvals_reviewer
            FROM chat_run_execution_contexts
            """
        ).fetchone()
        assert row == (
            "developer",
            "full",
            "owner",
            "repository",
            "danger-full-access",
            "never",
            None,
        )
    finally:
        database.close()


def test_developer_auto_access_is_strict_and_audited(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "developer-auto-access.db"
    settings = replace(
        _settings(database_path),
        direct_model_runtime_enabled=True,
        developer_agent_enabled=True,
        developer_workspace_root=tmp_path,
    )

    def terminal_execute(
        run_settings,
        accepted,
        _runtime_registry,
        *,
        cancellation_signal=None,
    ):
        del cancellation_signal
        _finish_error(
            run_settings,
            accepted,
            DirectModelError("test_complete", "Test completed."),
        )

    monkeypatch.setattr(
        "app.chat.execution_adapter.execute_direct_run",
        terminal_execute,
    )

    with TestClient(create_app(settings)) as client:
        registered = _register(
            client,
            email="owner@example.com",
            name="Owner",
        )
        assert registered.status_code == 201
        promote_registered_owner(settings, email="owner@example.com")
        csrf = client.cookies.get("kolibri_v3_csrf")
        assert csrf
        payload = json.loads(
            (
                Path(__file__).parents[2]
                / "contracts/v1/chat/examples/valid-ag-ui-run-input.json"
            ).read_text(encoding="utf-8")
        )

        mismatched = {
            **payload,
            "forwardedProps": {
                **payload["forwardedProps"],
                "executionMode": "developer",
                "accessMode": "standard",
            },
        }
        rejected = client.post(
            "/v1/chat/ag-ui",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json=mismatched,
        )
        assert rejected.status_code == 422

        _configure_owner_codex_selection(
            client,
            database_path=database_path,
            tenant_id=registered.json()["user"]["tenantId"],
            csrf=str(csrf),
        )

        accepted = client.post(
            "/v1/chat/ag-ui",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={
                **payload,
                "runId": "run_developer_auto_access_01",
                "forwardedProps": {
                    **payload["forwardedProps"],
                    "executionMode": "developer",
                    "accessMode": "auto",
                    "agentProfile": "codex-cli",
                },
            },
        )
        assert accepted.status_code == 200

    database = sqlite3.connect(database_path)
    try:
        row = database.execute(
            """
            SELECT execution_mode, access_mode, sandbox_profile,
                   approval_policy, approvals_reviewer
            FROM chat_run_execution_contexts
            """
        ).fetchone()
        assert row == (
            "developer",
            "auto",
            "workspace-write",
            "on-request",
            "auto_review",
        )
    finally:
        database.close()


def test_provider_admin_context_requires_owner_and_csrf(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "provider-admin.db")
    with TestClient(create_app(settings)) as client:
        owner = _register(client, email="owner@example.com", name="Owner")
        assert owner.status_code == 201
        assert owner.json()["user"]["role"] == "user"
        assert (
            client.get("/v1/internal/provider-admin-context").status_code
            == 403
        )
        promote_registered_owner(settings, email="owner@example.com")

        read_context = client.get("/v1/internal/provider-admin-context")
        assert read_context.status_code == 200
        assert read_context.json()["role"] == "superadmin"
        assert read_context.json()["csrfVerified"] is False

        denied = client.post(
            "/v1/internal/provider-admin-context",
            headers=ORIGIN,
        )
        assert denied.status_code == 403
        assert denied.json()["code"] == "csrf_token_required"

        csrf = client.cookies.get("kolibri_v3_csrf")
        approved = client.post(
            "/v1/internal/provider-admin-context",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
        )
        assert approved.status_code == 200
        assert approved.json()["csrfVerified"] is True
        assert approved.json()["subjectId"] == owner.json()["user"]["id"]

        regular = _register(client, email="person@example.com", name="Person")
        assert regular.status_code == 201
        regular_csrf = client.cookies.get("kolibri_v3_csrf")
        forbidden = client.post(
            "/v1/internal/provider-admin-context",
            headers={**ORIGIN, "X-CSRF-Token": regular_csrf},
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["code"] == "owner_required"


def test_login_is_origin_checked_and_throttled_without_storing_raw_email(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "throttle.db"
    settings = _settings(database_path)
    with TestClient(create_app(settings)) as client:
        assert _register(client, email="owner@example.com").status_code == 201

        wrong_origin = client.post(
            "/v1/auth/login",
            headers={"Origin": "https://attacker.example"},
            json={"email": "owner@example.com", "password": "wrong-password"},
        )
        assert wrong_origin.status_code == 403

        for _ in range(5):
            rejected = client.post(
                "/v1/auth/login",
                headers=ORIGIN,
                json={
                    "email": "owner@example.com",
                    "password": "wrong-password",
                },
            )
            assert rejected.status_code == 401
            assert rejected.json()["code"] == "invalid_credentials"

        blocked = client.post(
            "/v1/auth/login",
            headers=ORIGIN,
            json={"email": "owner@example.com", "password": PASSWORD},
        )
        assert blocked.status_code == 429
        assert blocked.json()["code"] == "login_temporarily_locked"

    database = sqlite3.connect(database_path)
    try:
        throttle_key = database.execute(
            "SELECT key_hash FROM auth_throttles"
        ).fetchone()[0]
        assert len(throttle_key) == 64
        assert "owner@example.com" not in throttle_key
    finally:
        database.close()


def test_login_from_another_client_keeps_existing_session_active(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "concurrent-sessions.db")
    app = create_app(settings)
    with TestClient(app) as first_client, TestClient(app) as second_client:
        registered = _register(
            first_client,
            email="owner@example.com",
            name="Owner",
        )
        assert registered.status_code == 201

        signed_in = second_client.post(
            "/v1/auth/login",
            headers=ORIGIN,
            json={"email": "owner@example.com", "password": PASSWORD},
        )
        assert signed_in.status_code == 200
        assert signed_in.json()["authenticated"] is True

        assert first_client.get("/v1/session").json()["authenticated"] is True
        assert second_client.get("/v1/session").json()["authenticated"] is True

    database = sqlite3.connect(tmp_path / "concurrent-sessions.db")
    try:
        assert (
            database.execute(
                """
                SELECT COUNT(*)
                FROM sessions
                WHERE revoked_at IS NULL AND expires_at > strftime('%s', 'now')
                """
            ).fetchone()[0]
            == 2
        )
    finally:
        database.close()


def test_development_first_user_stays_unprivileged_until_trusted_bootstrap(
    tmp_path: Path,
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'local.db'}",
        allowed_origins=("http://127.0.0.1:3103",),
        bootstrap_owner_email=None,
        environment="development",
        cookie_secure=False,
        csrf_secret=b"local-development-secret-at-least-32",
    )
    with TestClient(
        create_app(settings),
        base_url="http://127.0.0.1:3103",
    ) as client:
        response = client.post(
            "/v1/auth/register",
            headers={"Origin": "http://127.0.0.1:3103"},
            json={
                "email": "local-owner@example.com",
                "name": "Local Owner",
                "password": PASSWORD,
            },
        )
        assert response.status_code == 201
        assert response.json()["user"]["role"] == "user"
        promote_registered_owner(
            settings,
            email="local-owner@example.com",
        )
        assert client.get("/v1/session").json()["user"]["role"] == "owner"


def test_new_account_has_honest_empty_chat_history(
    tmp_path: Path,
) -> None:
    settings = replace(
        _settings(tmp_path / "empty-chat.db"),
        product_authority_id=None,
        product_authority_epoch=None,
        product_authority_placement_id=None,
        product_authorization_decision_id=None,
    )
    with TestClient(create_app(settings)) as anonymous:
        unauthorized = anonymous.get("/v1/chat/threads")
        assert unauthorized.status_code == 401

    with TestClient(create_app(settings)) as client:
        assert _register(client, email="owner@example.com").status_code == 201
        threads = client.get("/v1/chat/threads")
        assert threads.status_code == 200
        assert threads.headers["cache-control"] == "no-store"
        assert threads.json() == {"threads": [], "nextCursor": None}

        run_payload = json.loads(
            (
                Path(__file__).parents[2]
                / "contracts/v1/chat/examples/valid-ag-ui-run-input.json"
            ).read_text(encoding="utf-8")
        )
        without_csrf = client.post(
            "/v1/chat/ag-ui",
            headers=ORIGIN,
            json=run_payload,
        )
        assert without_csrf.status_code == 403

        csrf = client.cookies.get("kolibri_v3_csrf")
        unavailable = client.post(
            "/v1/chat/ag-ui",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json=run_payload,
        )
        assert unavailable.status_code == 503
        assert unavailable.json()["code"] == "chat_runtime_not_configured"
        assert unavailable.headers["cache-control"] == "no-store"


def test_new_run_can_reuse_the_same_user_message_without_409(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "repeat-answer.db"
    settings = replace(
        _settings(database_path),
        direct_model_runtime_enabled=True,
    )
    with TestClient(create_app(settings)) as client:
        assert _register(client, email="repeat@example.com").status_code == 201
        csrf = client.cookies.get("kolibri_v3_csrf")
        payload = json.loads(
            (
                Path(__file__).parents[2]
                / "contracts/v1/chat/examples/valid-ag-ui-run-input.json"
            ).read_text(encoding="utf-8")
        )

        first = client.post(
            "/v1/chat/ag-ui",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json=payload,
        )
        assert first.status_code == 200

        repeated = client.post(
            "/v1/chat/ag-ui",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={**payload, "runId": "run_repeat_answer_02"},
        )
        assert repeated.status_code == 200

        changed_input = client.post(
            "/v1/chat/ag-ui",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={
                **payload,
                "runId": "run_repeat_answer_02",
                "messages": [
                    {
                        **payload["messages"][-1],
                        "id": "message_changed_input_02",
                        "content": "Новый вход того же transport run.",
                    }
                ],
            },
        )
        assert changed_input.status_code == 200

    database = sqlite3.connect(database_path)
    try:
        assert database.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE role = 'user'"
        ).fetchone()[0] == 2
        assert database.execute(
            "SELECT COUNT(*) FROM chat_runs"
        ).fetchone()[0] == 3
    finally:
        database.close()


def test_thread_actions_are_user_scoped_audited_and_preserve_project_data(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "thread-actions.db"
    settings = replace(
        _settings(database_path),
        direct_model_runtime_enabled=True,
    )
    with TestClient(create_app(settings)) as client:
        assert _register(client, email="threads@example.com").status_code == 201
        csrf = client.cookies.get("kolibri_v3_csrf")
        assert csrf
        payload = json.loads(
            (
                Path(__file__).parents[2]
                / "contracts/v1/chat/examples/valid-ag-ui-run-input.json"
            ).read_text(encoding="utf-8")
        )
        accepted = client.post(
            "/v1/chat/ag-ui",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json=payload,
        )
        assert accepted.status_code == 200

        listed = client.get("/v1/chat/threads")
        assert listed.status_code == 200
        [thread] = listed.json()["threads"]
        assert thread["pinned"] is False
        thread_id = thread["id"]
        project_id = thread["projectId"]

        without_csrf = client.patch(
            f"/v1/chat/threads/{thread_id}",
            headers=ORIGIN,
            json={"action": "pin"},
        )
        assert without_csrf.status_code == 403

        for action in ("pin", "archive"):
            updated = client.patch(
                f"/v1/chat/threads/{thread_id}",
                headers={**ORIGIN, "X-CSRF-Token": csrf},
                json={"action": action},
            )
            assert updated.status_code == 204

        [thread] = client.get("/v1/chat/threads").json()["threads"]
        assert thread["pinned"] is True
        assert thread["status"] == "archived"

        removed = client.patch(
            f"/v1/chat/threads/{thread_id}",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={"action": "remove"},
        )
        assert removed.status_code == 204
        assert client.get("/v1/chat/threads").json()["threads"] == []

    database = sqlite3.connect(database_path)
    try:
        assert database.execute(
            "SELECT COUNT(*) FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()[0] == 1
        assert database.execute(
            "SELECT COUNT(*) FROM chat_messages"
        ).fetchone()[0] >= 1
        assert database.execute(
            """
            SELECT GROUP_CONCAT(action, ',')
            FROM chat_thread_user_events
            ORDER BY created_at
            """
        ).fetchone()[0] == "pin,archive,remove"
    finally:
        database.close()


def test_assistant_message_feedback_is_user_scoped_and_audited(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "message-feedback.db"
    settings = replace(
        _settings(database_path),
        direct_model_runtime_enabled=True,
    )
    with TestClient(create_app(settings)) as client:
        assert _register(client, email="feedback@example.com").status_code == 201
        csrf = client.cookies.get("kolibri_v3_csrf")
        assert csrf
        payload = json.loads(
            (
                Path(__file__).parents[2]
                / "contracts/v1/chat/examples/valid-ag-ui-run-input.json"
            ).read_text(encoding="utf-8")
        )
        accepted = client.post(
            "/v1/chat/ag-ui",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json=payload,
        )
        assert accepted.status_code == 200

        [thread] = client.get("/v1/chat/threads").json()["threads"]
        database = sqlite3.connect(database_path)
        try:
            internal = database.execute(
                """
                SELECT id, project_id, message_count
                FROM chat_threads
                LIMIT 1
                """
            ).fetchone()
            assistant_id = "message_feedback_assistant_01"
            tool_result_alias = "message_feedback_tool_result_01"
            database.execute(
                """
                INSERT INTO chat_messages (
                    tenant_id, id, project_id, thread_id, sequence,
                    client_message_id, run_id, role, content_text,
                    created_by_user_id, created_at
                )
                SELECT tenant_id, ?, project_id, id, message_count + 1,
                       ?, NULL, 'assistant', ?, NULL, ?
                FROM chat_threads
                WHERE id = ?
                """,
                (
                    assistant_id,
                    assistant_id,
                    "Тестовый ответ Kolibri.",
                    "2026-07-29T00:00:00+00:00",
                    internal[0],
                ),
            )
            run = database.execute(
                """
                SELECT id
                FROM chat_runs
                WHERE thread_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (internal[0],),
            ).fetchone()
            event_sequence = database.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) + 1
                FROM chat_run_events
                WHERE run_id = ?
                """,
                (run[0],),
            ).fetchone()[0]
            database.execute(
                """
                UPDATE chat_runs
                SET assistant_message_id = ?
                WHERE id = ?
                """,
                (assistant_id, run[0]),
            )
            database.execute(
                """
                INSERT INTO chat_run_events (
                    tenant_id, event_id, run_id, sequence, event_type,
                    event_json, created_at
                )
                SELECT tenant_id, ?, id, ?, 'TOOL_CALL_RESULT', ?, ?
                FROM chat_runs
                WHERE id = ?
                """,
                (
                    "event_feedback_tool_alias_01",
                    event_sequence,
                    json.dumps(
                        {
                            "type": "TOOL_CALL_RESULT",
                            "messageId": tool_result_alias,
                            "toolCallId": "tool_feedback_alias_01",
                            "content": "{}",
                            "role": "tool",
                        }
                    ),
                    "2026-07-29T00:00:01+00:00",
                    run[0],
                ),
            )
            database.commit()
        finally:
            database.close()

        without_csrf = client.put(
            (
                f"/v1/chat/threads/{thread['id']}/messages/"
                f"{assistant_id}/feedback"
            ),
            headers=ORIGIN,
            json={"type": "positive"},
        )
        assert without_csrf.status_code == 403

        for feedback_type in ("positive", "negative"):
            updated = client.put(
                (
                    f"/v1/chat/threads/{thread['id']}/messages/"
                    f"{assistant_id}/feedback"
                ),
                headers={**ORIGIN, "X-CSRF-Token": csrf},
                json={"type": feedback_type},
            )
            assert updated.status_code == 204

        aliased_feedback = client.put(
            (
                f"/v1/chat/threads/{thread['id']}/messages/"
                f"{tool_result_alias}/feedback"
            ),
            headers={**ORIGIN, "X-CSRF-Token": csrf},
            json={"type": "positive"},
        )
        assert aliased_feedback.status_code == 204

    database = sqlite3.connect(database_path)
    try:
        assert database.execute(
            "SELECT feedback_type FROM chat_message_feedback"
        ).fetchone()[0] == "positive"
        assert database.execute(
            "SELECT COUNT(*) FROM chat_message_feedback_events"
        ).fetchone()[0] == 3
    finally:
        database.close()
