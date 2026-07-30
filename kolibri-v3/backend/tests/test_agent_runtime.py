from __future__ import annotations

from dataclasses import replace
import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.agent_runtime import (
    AGENT_ACTIVITY_SCHEMA_ID,
    AGENT_ACTIVITY_SCHEMA_VERSION,
    AGENT_RUNTIME_SCHEMA_ID,
    AGENT_RUNTIME_SCHEMA_VERSION,
    AgentAccessPolicy,
    AgentExecutionConfiguration,
    AgentModelSelection,
    AgentRuntimeCapabilities,
    AgentRuntimeDescriptor,
    AgentRuntimeError,
    AgentRuntimeMessage,
    AgentRuntimeRegistry,
    AgentRuntimeRequest,
    AgentRuntimeResult,
    AgentWorkspace,
    DelegatingAgentRuntime,
    canonical_runtime_activity,
)
from app.config import Settings
from app.direct_model_runtime import (
    _mimo_runtime_adapter,
    execute_direct_run,
)
from app.main import create_app


def test_activity_protocol_normalizes_provider_command_events() -> None:
    started = canonical_runtime_activity(
        "started",
        {
            "id": "tool-1",
            "type": "commandExecution",
            "command": "pwd",
            "cwd": "/workspace",
        },
    )
    completed = canonical_runtime_activity(
        "completed",
        {
            "id": "tool-1",
            "type": "commandExecution",
            "command": "pwd",
            "cwd": "/workspace",
            "status": "completed",
            "exitCode": 0,
            "durationMs": 12,
            "output": "/workspace",
        },
    )

    assert started == {
        "schemaId": AGENT_ACTIVITY_SCHEMA_ID,
        "schemaVersion": AGENT_ACTIVITY_SCHEMA_VERSION,
        "id": "tool-1",
        "type": "commandExecution",
        "status": "inProgress",
        "command": "pwd",
        "cwd": "/workspace",
    }
    assert completed["schemaId"] == AGENT_ACTIVITY_SCHEMA_ID
    assert completed["output"] == "/workspace"
    assert completed["durationMs"] == 12


def test_activity_protocol_rejects_provider_specific_ui_events() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        canonical_runtime_activity(
            "started",
            {
                "id": "provider-card-1",
                "type": "mimoCustomCard",
            },
        )


def _chat_request(*, run_id: str = "run_runtime_contract_01") -> AgentRuntimeRequest:
    return AgentRuntimeRequest(
        tenant_id="tenant_runtime_contract",
        thread_id="thread_runtime_contract",
        run_id=run_id,
        credential_tenant_id="tenant_runtime_contract",
        mode="chat",
        execution_profile="chat",
        messages=(AgentRuntimeMessage(role="user", content="Проверь контракт."),),
        initial_prompt="Проверь контракт.",
        followup_prompt="Проверь контракт.",
        instructions="Верни короткий проверяемый ответ.",
        timeout_seconds=10,
    )


def _runtime(
    profile_id: str,
    *,
    calls: list[AgentRuntimeRequest],
    lifecycle: list[str],
    priority: int,
) -> DelegatingAgentRuntime:
    descriptor = AgentRuntimeDescriptor(
        profile_id=profile_id,
        runtime_id=f"{profile_id}-runtime",
        display_name=profile_id,
        auto_priority=priority,
        capabilities=AgentRuntimeCapabilities(
            modes=frozenset({"chat"}),
            streaming=True,
            structured_output=False,
            activity_events=False,
            persistent_sessions=True,
        ),
    )

    def execute(request: AgentRuntimeRequest) -> AgentRuntimeResult:
        calls.append(request)
        return AgentRuntimeResult(text=f"{profile_id}:ok")

    return DelegatingAgentRuntime(
        descriptor=descriptor,
        execute=execute,
        start=lambda: lifecycle.append(f"start:{profile_id}"),
        close=lambda: lifecycle.append(f"close:{profile_id}"),
    )


def test_registry_accepts_arbitrary_third_agent_and_swaps_same_request() -> None:
    calls_a: list[AgentRuntimeRequest] = []
    calls_b: list[AgentRuntimeRequest] = []
    lifecycle: list[str] = []
    registry = AgentRuntimeRegistry()
    registry.register(
        _runtime(
            "third-agent",
            calls=calls_a,
            lifecycle=lifecycle,
            priority=5,
        )
    )
    registry.register(
        _runtime(
            "another-agent",
            calls=calls_b,
            lifecycle=lifecycle,
            priority=10,
        )
    )

    assert registry.start_all() == {}
    request = _chat_request()
    first = registry.require("third-agent").execute(request)
    second = registry.require("another-agent").execute(request)
    assert calls_a == [request]
    assert calls_b == [request]
    assert first.text == "third-agent:ok"
    assert second.text == "another-agent:ok"
    assert registry.close_all() == {}
    assert lifecycle == [
        "start:third-agent",
        "start:another-agent",
        "close:another-agent",
        "close:third-agent",
    ]
    assert request.schema_id == AGENT_RUNTIME_SCHEMA_ID
    assert request.schema_version == AGENT_RUNTIME_SCHEMA_VERSION


def test_direct_executor_accepts_only_the_provider_neutral_registry() -> None:
    assert tuple(inspect.signature(execute_direct_run).parameters) == (
        "settings",
        "accepted",
        "runtime_registry",
        "cancellation_signal",
    )
    source = inspect.getsource(execute_direct_run)
    assert "codex-cli" not in source
    assert "mimo-code" not in source


def test_explicit_runtime_never_falls_back_to_another_registered_agent() -> None:
    registry = AgentRuntimeRegistry()
    lifecycle: list[str] = []
    registry.register(
        _runtime(
            "healthy-agent",
            calls=[],
            lifecycle=lifecycle,
            priority=1,
        )
    )

    with pytest.raises(AgentRuntimeError) as error:
        registry.resolve(
            requested_profile="missing-agent",
            connected_profiles={"healthy-agent": "tenant_credentials"},
        )

    assert error.value.code == "agent_runtime_not_registered"


def test_fastapi_lifespan_starts_and_closes_the_registered_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle: list[str] = []
    registry = AgentRuntimeRegistry()
    registry.register(
        _runtime(
            "third-agent",
            calls=[],
            lifecycle=lifecycle,
            priority=1,
        )
    )
    monkeypatch.setattr(
        main_module,
        "build_agent_runtime_registry",
        lambda *_args, **_kwargs: registry,
    )
    settings = replace(
        Settings.for_testing(database_url=tmp_path / "app.db"),
        direct_model_runtime_enabled=True,
    )

    with TestClient(create_app(settings)) as client:
        assert client.app.state.agent_runtime_registry is registry
        assert lifecycle == ["start:third-agent"]

    assert lifecycle == ["start:third-agent", "close:third-agent"]


class _PersistentDeveloperTransport:
    def __init__(self) -> None:
        self.start_calls = 0
        self.close_calls = 0
        self.complete_calls: list[dict[str, Any]] = []

    def start(self) -> None:
        self.start_calls += 1

    def close(self) -> None:
        self.close_calls += 1

    def complete(self, **kwargs: Any) -> SimpleNamespace:
        self.complete_calls.append(kwargs)
        kwargs["on_delta"]("ok")
        return SimpleNamespace(
            text="Готово.",
            session_id="ses_runtime_contract",
        )


def _developer_request(workspace: Path, run_id: str) -> AgentRuntimeRequest:
    return AgentRuntimeRequest(
        tenant_id="tenant_runtime_contract",
        thread_id="thread_runtime_contract",
        run_id=run_id,
        credential_tenant_id="tenant_runtime_contract",
        mode="developer",
        execution_profile="developer",
        messages=(AgentRuntimeMessage(role="user", content="Проверь репозиторий."),),
        initial_prompt="Проверь репозиторий.",
        followup_prompt="Проверь репозиторий.",
        instructions="Соблюдай локальные инструкции.",
        timeout_seconds=10,
        configuration=AgentExecutionConfiguration(
            selection=AgentModelSelection(),
            access=AgentAccessPolicy(
                mode="full",
                sandbox="danger-full-access",
                approval_policy="never",
            ),
            workspace=AgentWorkspace(
                reference="repository",
                root=workspace,
            ),
        ),
    )


def test_two_developer_turns_reuse_one_runtime_session_key(
    tmp_path: Path,
) -> None:
    transport = _PersistentDeveloperTransport()
    runtime = _mimo_runtime_adapter(
        Settings.for_testing(database_url=tmp_path / "runtime.db"),
        client_transport=None,
        developer_transport=transport,
    )
    registry = AgentRuntimeRegistry()
    registry.register(runtime)

    registry.start_all()
    first = runtime.execute(_developer_request(tmp_path, "run_runtime_contract_01"))
    second = runtime.execute(_developer_request(tmp_path, "run_runtime_contract_02"))
    registry.close_all()

    assert transport.start_calls == 1
    assert transport.close_calls == 1
    assert len(transport.complete_calls) == 2
    assert {call["conversation_key"] for call in transport.complete_calls} == {
        "tenant_runtime_contract:thread_runtime_contract:mimo-code-runtime"
    }
    assert first.session_id == second.session_id == "ses_runtime_contract"
