from __future__ import annotations

from dataclasses import replace
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.direct_model_runtime as direct_model_runtime_module
import app.main as main_module
from app.agent_runtime import (
    AGENT_RUNTIME_SCHEMA_ID,
    AGENT_RUNTIME_SCHEMA_VERSION,
    LIVE_WEB_SEARCH_CAPABILITY_ID,
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
)
from app.config import Settings
from app.direct_model_runtime import (
    _mimo_runtime_adapter,
    execute_direct_run,
)
from app.main import create_app


def _chat_request(*, run_id: str = "run_runtime_contract_01") -> AgentRuntimeRequest:
    return AgentRuntimeRequest(
        tenant_id="tenant_runtime_contract",
        user_id="user_runtime_contract",
        project_id="project_runtime_contract",
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


def test_runtime_capability_metadata_is_bounded_and_provider_neutral() -> None:
    capabilities = AgentRuntimeCapabilities(
        modes=frozenset({"chat"}),
        streaming=True,
        structured_output=False,
        activity_events=False,
        persistent_sessions=True,
        capability_ids=frozenset({LIVE_WEB_SEARCH_CAPABILITY_ID}),
    )

    assert capabilities.capability_ids == frozenset(
        {LIVE_WEB_SEARCH_CAPABILITY_ID}
    )
    with pytest.raises(ValueError, match="capability id"):
        AgentRuntimeCapabilities(
            modes=frozenset({"chat"}),
            streaming=True,
            structured_output=False,
            activity_events=False,
            persistent_sessions=True,
            capability_ids=frozenset({"not a capability"}),
        )


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
        user_id="user_runtime_contract",
        project_id="project_runtime_contract",
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


class _StructuredMimoResponse:
    status_code = 200

    @staticmethod
    def json() -> dict[str, Any]:
        return {"choices": [{"message": {"content": "{}"}}]}


class _RecordingStructuredMimoTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, *, api_key: str, payload: dict[str, Any]):
        self.calls.append(
            {
                "url": url,
                "api_key": api_key,
                "payload": payload,
            }
        )
        return _StructuredMimoResponse()


class _FailingCodexTransport:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def complete(self, **_kwargs: Any) -> None:
        raise self.error


def test_mimo_structured_profile_sends_complete_initial_prompt_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        direct_model_runtime_module,
        "load_mimo_key",
        lambda _settings, *, tenant_id: f"test-key-for-{tenant_id}",
    )
    transport = _RecordingStructuredMimoTransport()
    runtime = _mimo_runtime_adapter(
        Settings.for_testing(database_url=tmp_path / "runtime.db"),
        client_transport=transport,  # type: ignore[arg-type]
        developer_transport=None,
    )
    complete_stage_input = (
        "CANONICAL_CONVERSATION_IN_INITIAL_PROMPT\n"
        "PROJECT_CASE_SENTINEL\nATTACHMENT_CHUNK_SENTINEL"
    )
    request = AgentRuntimeRequest(
        tenant_id="tenant_runtime_contract",
        user_id="user_runtime_contract",
        project_id="project_runtime_contract",
        thread_id="thread_runtime_contract",
        run_id="run_runtime_contract_structured",
        credential_tenant_id="tenant_runtime_contract",
        mode="structured",
        execution_profile="estimate-plan",
        messages=(
            AgentRuntimeMessage(
                role="user",
                content="RAW_CANONICAL_MESSAGE_MUST_NOT_BE_DUPLICATED",
            ),
        ),
        initial_prompt=complete_stage_input,
        followup_prompt=complete_stage_input,
        instructions="Верни только JSON.",
        timeout_seconds=10,
        output_schema={"type": "object"},
    )

    result = runtime.execute(request)

    assert result.text == "{}"
    assert len(transport.calls) == 1
    [system_message, user_message] = transport.calls[0]["payload"]["messages"]
    assert system_message["role"] == "system"
    assert user_message == {"role": "user", "content": complete_stage_input}
    payload_text = json.dumps(
        transport.calls[0]["payload"]["messages"],
        ensure_ascii=False,
    )
    assert "PROJECT_CASE_SENTINEL" in payload_text
    assert "ATTACHMENT_CHUNK_SENTINEL" in payload_text
    assert "RAW_CANONICAL_MESSAGE_MUST_NOT_BE_DUPLICATED" not in payload_text


@pytest.mark.parametrize("mode", ["chat", "structured"])
def test_codex_and_mimo_transient_failures_share_retry_contract(
    mode: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_request(*_args: Any, **_kwargs: Any) -> None:
        raise direct_model_runtime_module.DirectModelError(
            "mimo_request_failed",
            "MiMo Code сейчас недоступен. Повторите запрос.",
        )

    monkeypatch.setattr(
        direct_model_runtime_module,
        (
            "_mimo_structured_response"
            if mode == "structured"
            else "_mimo_response"
        ),
        fail_request,
    )
    settings = Settings.for_testing(database_url=tmp_path / "runtime.db")
    runtimes = (
        (
            direct_model_runtime_module._codex_runtime_adapter(
                settings,
                _FailingCodexTransport(
                    direct_model_runtime_module.CodexAppServerError(
                        "temporary Codex transport failure"
                    )
                ),
            ),
            "codex_request_failed",
        ),
        (
            _mimo_runtime_adapter(
                settings,
                client_transport=object(),
                developer_transport=None,
            ),
            "mimo_request_failed",
        ),
    )
    request = _chat_request(run_id=f"run_mimo_{mode}_transport_failure")
    if mode == "structured":
        request = replace(
            request,
            mode="structured",
            execution_profile="estimate-plan",
            output_schema={"type": "object"},
        )

    errors: list[AgentRuntimeError] = []
    for runtime, expected_code in runtimes:
        with pytest.raises(AgentRuntimeError) as error:
            runtime.execute(request)
        assert error.value.code == expected_code
        errors.append(error.value)

    assert {(error.category, error.retryable) for error in errors} == {
        ("unavailable", True)
    }


@pytest.mark.parametrize(
    "error_code",
    [
        "mimo_api_key_rejected",
        "mimo_base_url_invalid",
        "mimo_web_search_unavailable",
    ],
)
def test_mimo_client_policy_and_configuration_failures_are_not_retryable(
    error_code: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_request(*_args: Any, **_kwargs: Any) -> None:
        raise direct_model_runtime_module.DirectModelError(
            error_code,
            "Проверяемая ошибка MiMo.",
        )

    monkeypatch.setattr(
        direct_model_runtime_module,
        "_mimo_structured_response",
        fail_request,
    )
    runtime = _mimo_runtime_adapter(
        Settings.for_testing(database_url=tmp_path / "runtime.db"),
        client_transport=object(),
        developer_transport=None,
    )
    request = replace(
        _chat_request(run_id=f"run_mimo_{error_code}"),
        mode="structured",
        execution_profile="estimate-plan",
        output_schema={"type": "object"},
    )

    with pytest.raises(AgentRuntimeError) as error:
        runtime.execute(request)

    assert error.value.code == error_code
    assert error.value.retryable is False


def test_codex_auth_and_configuration_failures_are_not_retryable(
    tmp_path: Path,
) -> None:
    settings = Settings.for_testing(database_url=tmp_path / "runtime.db")
    auth_runtime = direct_model_runtime_module._codex_runtime_adapter(
        settings,
        _FailingCodexTransport(
            direct_model_runtime_module.CodexAppServerAuthenticationError(
                "Codex login required"
            )
        ),
    )
    config_runtime = direct_model_runtime_module._codex_runtime_adapter(
        settings,
        object(),
    )
    config_request = replace(
        _chat_request(run_id="run_codex_configuration_failure"),
        configuration=AgentExecutionConfiguration(
            selection=AgentModelSelection(model_id="gpt-test-only"),
        ),
    )

    errors: list[AgentRuntimeError] = []
    with pytest.raises(AgentRuntimeError) as auth_error:
        auth_runtime.execute(_chat_request(run_id="run_codex_auth_failure"))
    errors.append(auth_error.value)
    with pytest.raises(AgentRuntimeError) as config_error:
        config_runtime.execute(config_request)
    errors.append(config_error.value)

    assert auth_error.value.category == "authentication"
    assert config_error.value.category == "configuration"
    assert all(error.retryable is False for error in errors)


@pytest.mark.parametrize(
    ("adapter_name", "response_name", "error_code", "retryable"),
    [
        ("_openai_runtime_adapter", "_openai_response", "openai_rate_limited", True),
        ("_openai_runtime_adapter", "_openai_response", "openai_request_failed", True),
        ("_openai_runtime_adapter", "_openai_response", "openai_api_key_rejected", False),
        ("_qwen_runtime_adapter", "_qwen_response", "qwen_rate_limited", True),
        ("_qwen_runtime_adapter", "_qwen_response", "qwen_request_failed", True),
        ("_deepseek_runtime_adapter", "_deepseek_response", "deepseek_rate_limited", True),
        (
            "_deepseek_runtime_adapter",
            "_deepseek_response",
            "custom_model_rate_limited",
            True,
        ),
        ("_gemini_runtime_adapter", "_gemini_response", "gemini_rate_limited", True),
        ("_gemini_runtime_adapter", "_gemini_response", "gemini_api_key_rejected", False),
    ],
)
def test_key_backed_provider_errors_follow_neutral_retry_contract(
    adapter_name: str,
    response_name: str,
    error_code: str,
    retryable: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 429 rate limits and transient transport failures are retryable."""

    def fail_request(*_args: Any, **_kwargs: Any) -> None:
        raise direct_model_runtime_module.DirectModelError(
            error_code,
            "Проверяемая ошибка провайдера.",
        )

    monkeypatch.setattr(direct_model_runtime_module, response_name, fail_request)
    adapter = getattr(
        direct_model_runtime_module,
        adapter_name,
    )(
        Settings.for_testing(database_url=tmp_path / "runtime.db"),
        client_transport=object(),
    )

    with pytest.raises(AgentRuntimeError) as error:
        adapter.execute(_chat_request(run_id=f"run_{error_code}"))

    assert error.value.code == error_code
    assert error.value.retryable is retryable
