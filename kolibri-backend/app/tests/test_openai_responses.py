import asyncio
import json

import httpx
import pytest

from app import openai_responses


def _provider() -> dict:
    return {
        "id": "openai_codex",
        "url": "https://api.openai.test/v1/responses",
        "model": "gpt-5.6-sol",
        "key": "server-test-key",
        "protocol": "responses",
    }


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    openai_responses.reset_tool_probe_state()
    for name in (
        "OPENAI_REASONING_EFFORT",
        "OPENAI_REASONING_MODE",
        "OPENAI_REASONING_CONTEXT",
        "OPENAI_REASONING_SUMMARY",
        "OPENAI_VECTOR_STORE_IDS",
        "OPENAI_MCP_SERVER_URL",
        "OPENAI_MCP_SERVER_LABEL",
        "OPENAI_MCP_ALLOWED_TOOLS",
        "OPENAI_COMPUTER_ENABLED",
        "OPENAI_COMPUTER_SANDBOX_ATTESTED",
        "OPENAI_MULTI_AGENT_BETA_ENABLED",
        "OPENAI_MULTI_AGENT_MAX_CONCURRENCY",
    ):
        monkeypatch.delenv(name, raising=False)
    yield
    openai_responses.reset_tool_probe_state()


def _install_transport(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_client(transport=transport, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(openai_responses.httpx, "AsyncClient", client_factory)


def test_payload_uses_responses_reasoning_previous_id_and_model_alias(monkeypatch):
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "xhigh")
    monkeypatch.setenv("OPENAI_REASONING_MODE", "pro")
    monkeypatch.setenv("OPENAI_REASONING_CONTEXT", "all_turns")
    monkeypatch.setenv("OPENAI_REASONING_SUMMARY", "concise")
    payload, headers = openai_responses.build_response_payload(
        _provider(),
        [
            {"role": "system", "content": "System contract"},
            {"role": "user", "content": "Hello"},
        ],
        previous_response_id="resp_previous_123",
    )

    assert payload["model"] == "gpt-5.6-sol"
    assert payload["instructions"] == "System contract"
    assert payload["input"] == [{"role": "user", "content": "Hello"}]
    assert payload["previous_response_id"] == "resp_previous_123"
    assert payload["store"] is True
    assert payload["reasoning"] == {
        "effort": "xhigh",
        "context": "all_turns",
        "summary": "concise",
        "mode": "pro",
    }
    assert headers["Authorization"] == "Bearer server-test-key"


def test_tools_fail_closed_until_configuration_and_live_output(monkeypatch):
    tools = openai_responses.configured_tools()
    assert {tool["type"] for tool in tools} == {
        "web_search",
        "code_interpreter",
        "image_generation",
    }
    assert "file_search" not in {tool["type"] for tool in tools}
    assert "mcp" not in {tool["type"] for tool in tools}
    assert "computer" not in {tool["type"] for tool in tools}

    monkeypatch.setenv("OPENAI_VECTOR_STORE_IDS", "vs_1,vs_2")
    monkeypatch.setenv("OPENAI_MCP_SERVER_URL", "https://mcp.example.test/sse")
    monkeypatch.setenv("OPENAI_MCP_ALLOWED_TOOLS", "search,read")
    monkeypatch.setenv("OPENAI_COMPUTER_ENABLED", "true")
    tools = openai_responses.configured_tools()
    assert next(tool for tool in tools if tool["type"] == "file_search")["vector_store_ids"] == ["vs_1", "vs_2"]
    assert next(tool for tool in tools if tool["type"] == "mcp")["allowed_tools"] == ["search", "read"]
    assert "computer" not in {tool["type"] for tool in tools}

    manifest = openai_responses.responses_capability_manifest()
    web = next(item for item in manifest["capabilities"] if item["id"] == "openai.web_search")
    assert web["status"] == "unverified"
    assert web["invocable"] is False

    openai_responses.parse_response({
        "id": "resp_tool",
        "status": "completed",
        "output": [{"id": "ws_1", "type": "web_search_call", "status": "completed"}],
    })
    web = next(
        item
        for item in openai_responses.responses_capability_manifest()["capabilities"]
        if item["id"] == "openai.web_search"
    )
    assert web["status"] == "live"
    assert web["invocable"] is True
    assert web["verified_at"]


def test_multi_agent_beta_is_explicit_and_bounded(monkeypatch):
    payload, headers = openai_responses.build_response_payload(_provider(), [{"role": "user", "content": "Hi"}])
    assert "multi_agent" not in payload
    assert "OpenAI-Beta" not in headers

    monkeypatch.setenv("OPENAI_MULTI_AGENT_BETA_ENABLED", "true")
    monkeypatch.setenv("OPENAI_MULTI_AGENT_MAX_CONCURRENCY", "99")
    payload, headers = openai_responses.build_response_payload(_provider(), [{"role": "user", "content": "Hi"}])
    assert payload["multi_agent"] == {"enabled": True, "max_concurrent_subagents": 10}
    assert headers["OpenAI-Beta"] == "responses_multi_agent=v1"
    capability = next(
        item
        for item in openai_responses.responses_capability_manifest()["capabilities"]
        if item["id"] == "openai.multi_agent"
    )
    assert capability["beta"] is True
    assert capability["status"] == "unverified"
    assert capability["invocable"] is False


def test_client_policy_can_only_reduce_server_tools_and_select_bounded_mode(monkeypatch):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_IDS", "vs_server")
    monkeypatch.setenv("OPENAI_COMPUTER_ENABLED", "true")
    policy = {
        "mode": "deep",
        "reasoning_effort": "high",
        "tool_choice": "auto",
        "background": True,
        "allowed_capabilities": ["openai.web_search", "openai.computer", "unknown.tool"],
    }
    payload, headers = openai_responses.build_response_payload(
        _provider(),
        [{"role": "user", "content": "Research"}],
        policy=policy,
        idempotency_key="project:message-123",
    )

    # Computer remains disabled because the server sandbox attestation is
    # absent; file search remains disabled because the client did not allow it.
    assert payload["tools"] == [{"type": "web_search"}]
    assert payload["reasoning"]["effort"] == "high"
    assert payload["background"] is True
    assert headers["Idempotency-Key"] == "project:message-123"

    fast, _ = openai_responses.build_response_payload(
        _provider(),
        [{"role": "user", "content": "Hello"}],
        policy={
            "mode": "fast",
            "reasoning_effort": "high",
            "tool_choice": "auto",
            "background": True,
            "allowed_capabilities": [],
        },
    )
    assert fast["reasoning"]["effort"] == "low"
    assert fast["reasoning"]["summary"] == "concise"
    assert "background" not in fast
    assert "tools" not in fast
    assert payload["reasoning"]["summary"] == "auto"


def test_nonstream_response_maps_text_safe_summary_and_tools(monkeypatch):
    def upstream(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/responses"
        body = json.loads(request.content)
        assert body["model"] == "gpt-5.6-sol"
        return httpx.Response(200, json={
            "id": "resp_answer_1",
            "status": "completed",
            "model": "gpt-5.6-sol",
            "output": [
                {
                    "id": "reason_1",
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "Проверил входные данные."}],
                    "content": [{"type": "reasoning_text", "text": "PRIVATE RAW REASONING"}],
                },
                {"id": "ws_1", "type": "web_search_call", "status": "completed"},
                {
                    "id": "msg_1",
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Готовый ответ"}],
                },
            ],
        })

    _install_transport(monkeypatch, upstream)
    result = asyncio.run(openai_responses.create_response(_provider(), [{"role": "user", "content": "Ответь"}]))

    assert result["id"] == "resp_answer_1"
    assert result["content"] == "Готовый ответ"
    assert result["reasoning_summary"] == "Проверил входные данные."
    assert "PRIVATE" not in json.dumps(result, ensure_ascii=False)
    assert result["tool_events"][0]["type"] == "tool.completed"
    assert result["tool_events"][0]["tool"] == "web_search"


def test_stream_maps_text_reasoning_summary_and_tool_lifecycle(monkeypatch):
    events = [
        {"type": "response.created", "response": {"id": "resp_stream_1"}},
        {
            "type": "response.reasoning_summary_text.delta",
            "item_id": "reasoning-item-private-id",
            "output_index": 0,
            "summary_index": 0,
            "delta": "Проверяю ",
        },
        {
            "type": "response.reasoning_summary_text.delta",
            "item_id": "reasoning-item-private-id",
            "output_index": 0,
            "summary_index": 0,
            "delta": "источники",
        },
        {
            "type": "response.reasoning_summary_text.done",
            "item_id": "reasoning-item-private-id",
            "output_index": 0,
            "summary_index": 0,
            "text": "Проверяю источники",
        },
        {
            "type": "response.output_item.added",
            "item": {"id": "ws_1", "type": "web_search_call", "status": "in_progress"},
        },
        {"type": "response.output_text.delta", "delta": "Привет"},
        {
            "type": "response.output_item.done",
            "item": {"id": "ws_1", "type": "web_search_call", "status": "completed"},
        },
        {"type": "response.completed", "response": {"id": "resp_stream_1", "status": "completed"}},
    ]
    sse = "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events)

    def upstream(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["stream"] is True
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    _install_transport(monkeypatch, upstream)

    async def collect():
        return [event async for event in openai_responses.stream_response(
            _provider(), [{"role": "user", "content": "Привет"}]
        )]

    output = asyncio.run(collect())
    assert next(item for item in output if item.get("content"))["content"] == "Привет"
    summaries = [item["work_summary"] for item in output if item.get("work_summary")]
    assert [item["summary"] for item in summaries] == [
        "Проверяю",
        "Проверяю источники",
        "Проверяю источники",
    ]
    assert [item["status"] for item in summaries] == ["active", "active", "completed"]
    assert len({item["summary_id"] for item in summaries}) == 1
    assert len({item["step_id"] for item in summaries}) == 1
    assert all(item["kind"] == "reasoning_excerpt" for item in summaries)
    assert all(item["stage"] == "reasoning_summary" for item in summaries)
    assert all(item["occurred_at"] for item in summaries)
    assert "reasoning-item-private-id" not in json.dumps(summaries, ensure_ascii=False)
    assert [item["tool_event"]["type"] for item in output if item.get("tool_event")] == [
        "tool.started",
        "tool.completed",
    ]
    assert next(item["response_meta"] for item in output if item.get("response_meta"))["id"] == "resp_stream_1"


def test_stream_maps_upstream_work_summary_without_raw_ids_or_topology(monkeypatch):
    events = [
        {
            "type": "response.work_summary.updated",
            "response_id": "resp_stream_2",
            "sequence": 17,
            "work_summary": {
                "kind": "stage",
                "stage": "tool_execution",
                "status": "running",
                "step_id": "step_private_provider_123",
                "summary_id": "summary_private_provider_123",
                "summary": (
                    "Выполняю через Home Control Plane agent07 openai gpt-5.6-sol "
                    "token=sk-testtoken123456 http://localhost/internal node-03"
                ),
                "occurred_at": "2026-07-15T12:00:00Z",
                "provider": "openai",
                "model": "gpt-5.6-sol",
            },
        },
        {
            "type": "response.work_summary.updated",
            "response_id": "resp_stream_2",
            "sequence": 18,
            "work_summary": {
                "kind": "stage",
                "stage": "tool_execution",
                "status": "completed",
                "step_id": "step_private_provider_123",
                "summary_id": "summary_private_provider_123",
                "summary": "Выполнение завершено после проверки результата",
                "occurred_at": "2026-07-15T12:00:01Z",
            },
        },
        {
            "type": "response.work_summary.updated",
            "response_id": "resp_stream_2",
            "sequence": 19,
            "work_summary": {
                "stage": "reasoning_content",
                "summary": "PRIVATE RAW REASONING",
            },
        },
        {"type": "response.completed", "response": {"id": "resp_stream_2", "status": "completed"}},
    ]
    sse = "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events)

    def upstream(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    _install_transport(monkeypatch, upstream)

    async def collect():
        return [
            event async for event in openai_responses.stream_response(
                _provider(), [{"role": "user", "content": "Покажи ход работы"}]
            )
        ]

    output = asyncio.run(collect())
    summaries = [item for item in output if item.get("work_summary")]

    assert len(summaries) == 2
    assert [item["response_id"] for item in summaries] == ["resp_stream_2", "resp_stream_2"]
    assert [item["sequence"] for item in summaries] == [1, 2]
    first = summaries[0]["work_summary"]
    second = summaries[1]["work_summary"]
    assert first["stage"] == "tool_execution"
    assert first["status"] == "active"
    assert first["step_id"].startswith("step_")
    assert first["summary_id"].startswith("summary_")
    assert first["step_id"] == second["step_id"]
    assert first["summary_id"] == second["summary_id"]
    assert second["status"] == "completed"
    assert first["occurred_at"] == "2026-07-15T12:00:00+00:00"
    assert second["occurred_at"] == "2026-07-15T12:00:01+00:00"
    dumped = json.dumps(summaries, ensure_ascii=False)
    assert "step_private_provider_123" not in dumped
    assert "summary_private_provider_123" not in dumped
    assert "sk-testtoken123456" not in dumped
    assert "Home" not in dumped
    assert "Control Plane" not in dumped
    assert "agent07" not in dumped
    assert "node-03" not in dumped
    assert "gpt-5.6-sol" not in dumped
    assert "http://localhost/internal" not in dumped
    assert "PRIVATE RAW REASONING" not in dumped


def test_background_create_retrieve_resume_and_cancel(monkeypatch):
    seen: list[tuple[str, str, dict[str, str]]] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, dict(request.url.params)))
        if request.method == "POST" and request.url.path == "/v1/responses":
            body = json.loads(request.content)
            assert body["background"] is True
            assert body["store"] is True
            return httpx.Response(200, json={"id": "resp_bg_1", "status": "queued", "output": []})
        if request.method == "GET":
            return httpx.Response(200, json={"id": "resp_bg_1", "status": "in_progress", "output": []})
        return httpx.Response(200, json={"id": "resp_bg_1", "status": "cancelled", "output": []})

    _install_transport(monkeypatch, upstream)
    created = asyncio.run(openai_responses.create_response(
        _provider(), [{"role": "user", "content": "Long task"}], background=True
    ))
    retrieved = asyncio.run(openai_responses.retrieve_response(_provider(), "resp_bg_1"))
    resumed = asyncio.run(openai_responses.retrieve_response(
        _provider(), "resp_bg_1", stream=True, starting_after=42
    ))
    cancelled = asyncio.run(openai_responses.cancel_response(_provider(), "resp_bg_1"))

    assert created["status"] == "queued"
    assert retrieved["status"] == "in_progress"
    assert isinstance(resumed, httpx.Response)
    assert cancelled["status"] == "cancelled"
    assert seen == [
        ("POST", "/v1/responses", {}),
        ("GET", "/v1/responses/resp_bg_1", {}),
        ("GET", "/v1/responses/resp_bg_1", {"stream": "true", "starting_after": "42"}),
        ("POST", "/v1/responses/resp_bg_1/cancel", {}),
    ]


def test_invalid_response_id_is_rejected_before_network(monkeypatch):
    class ForbiddenClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("network must not run for an invalid response id")

    monkeypatch.setattr(openai_responses.httpx, "AsyncClient", ForbiddenClient)
    with pytest.raises(ValueError, match="invalid_response_id"):
        asyncio.run(openai_responses.cancel_response(_provider(), "../secrets"))
