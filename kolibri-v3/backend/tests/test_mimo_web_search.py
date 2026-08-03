from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import app.direct_model_runtime as direct_model_runtime
from app.agent_runtime import LIVE_WEB_SEARCH_CAPABILITY_ID
from app.config import Settings
from app.direct_model_runtime import (
    DirectModelError,
    MIMO_FUNCTION_TOOLS,
    MIMO_WEB_SEARCH_TOOL,
    _mimo_web_search_tool,
    _mimo_response,
    _mimo_runtime_adapter,
)


def test_mimo_search_is_forced_for_fresh_news_but_optional_for_stable_turns() -> None:
    assert _mimo_web_search_tool(
        [{"role": "user", "content": "Какие новости сегодня об ИИ?"}]
    )["force_search"] is True
    assert _mimo_web_search_tool(
        [{"role": "user", "content": "Объясни принцип SOLID."}]
    )["force_search"] is False


class _StreamResponse:
    def __init__(self, status_code: int, lines: list[str] | None = None) -> None:
        self.status_code = status_code
        self._lines = list(lines or [])
        self.closed = False

    def iter_lines(self):
        yield from self._lines

    def close(self) -> None:
        self.closed = True


class _RecordingMimoRuntime:
    def __init__(self, responses: list[_StreamResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def stream(self, url: str, *, api_key: str, payload: dict[str, Any]):
        self.calls.append(
            {
                "url": url,
                "api_key": api_key,
                "payload": payload,
            }
        )
        return self.responses.pop(0)


def _settings(tmp_path: Path) -> Settings:
    return Settings.for_testing(database_url=tmp_path / "mimo-web.db")


def _sse(delta: dict[str, Any]) -> str:
    return "data: " + json.dumps(
        {"choices": [{"delta": delta}]},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def test_mimo_chat_declares_live_web_search_and_streams_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        direct_model_runtime,
        "load_mimo_key",
        lambda _settings, *, tenant_id: f"test-key-for-{tenant_id}",
    )
    response = _StreamResponse(
        200,
        [
            _sse(
                {
                    "annotations": [
                        {
                            "type": "url_citation",
                            "url": "https://news.example.com/today",
                            "title": "Новости дня",
                            "summary": "Проверенное описание события.",
                            "site_name": "Example News",
                            "publish_time": "2026-08-01T09:00:00Z",
                        },
                        {
                            "url": "http://insecure.example.com/ignored",
                            "title": "Must be rejected",
                        },
                        {
                            "url": "https://127.0.0.1/private",
                            "title": "Must be rejected",
                        },
                    ]
                }
            ),
            _sse({"content": "Сегодня произошло проверенное событие."}),
            "data: [DONE]",
        ],
    )
    runtime = _RecordingMimoRuntime([response])
    deltas: list[str] = []
    activities: list[tuple[str, dict[str, Any]]] = []

    turn = _mimo_response(
        _settings(tmp_path),
        tenant_id="tenant-mimo-web",
        messages=[
            {
                "role": "user",
                "content": "Какие новости произошли сегодня?",
            }
        ],
        instructions="Отвечай по фактам.",
        runtime=runtime,  # type: ignore[arg-type]
        on_delta=deltas.append,
        on_activity=lambda phase, item: activities.append((phase, item)),
    )

    assert response.closed is True
    assert len(runtime.calls) == 1
    request = runtime.calls[0]
    assert request["url"].endswith("/v1/chat/completions")
    assert request["payload"]["tools"] == [
        {**MIMO_WEB_SEARCH_TOOL, "force_search": True},
        *MIMO_FUNCTION_TOOLS,
    ]
    [system_message, user_message] = request["payload"]["messages"]
    assert system_message["role"] == "system"
    assert "живой веб-поиск" in system_message["content"]
    assert "Отвечай по фактам." in system_message["content"]
    assert user_message["content"] == "Какие новости произошли сегодня?"

    assert [phase for phase, _item in activities] == ["started", "completed"]
    started = activities[0][1]
    completed = activities[1][1]
    assert started["type"] == completed["type"] == "webSearch"
    assert completed["status"] == "completed"
    assert completed["results"] == [
        {
            "url": "https://news.example.com/today",
            "title": "Новости дня",
            "summary": "Проверенное описание события.",
            "siteName": "Example News",
            "publishTime": "2026-08-01T09:00:00Z",
        }
    ]
    assert turn.text is not None
    assert "проверенное событие" in turn.text
    assert "https://news.example.com/today" in turn.text
    assert "Источники:" in turn.text
    assert "".join(deltas) == turn.text


def test_mimo_web_search_rejection_is_not_silently_retried_without_search(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        direct_model_runtime,
        "load_mimo_key",
        lambda _settings, *, tenant_id: f"test-key-for-{tenant_id}",
    )
    response = _StreamResponse(400)
    runtime = _RecordingMimoRuntime([response])

    with pytest.raises(DirectModelError) as error:
        _mimo_response(
            _settings(tmp_path),
            tenant_id="tenant-mimo-web",
            messages=[{"role": "user", "content": "Новости сегодня?"}],
            instructions="Отвечай по фактам.",
            runtime=runtime,  # type: ignore[arg-type]
            on_delta=lambda _delta: None,
        )

    assert error.value.code == "mimo_web_search_unavailable"
    assert response.closed is True
    assert len(runtime.calls) == 1
    assert runtime.calls[0]["payload"]["tools"] == [
        {**MIMO_WEB_SEARCH_TOOL, "force_search": True},
        *MIMO_FUNCTION_TOOLS,
    ]


def test_mimo_runtime_descriptor_publishes_live_web_search(
    tmp_path: Path,
) -> None:
    runtime = _mimo_runtime_adapter(
        _settings(tmp_path),
        client_transport=object(),
        developer_transport=None,
    )

    assert runtime.descriptor.capabilities.capability_ids == frozenset(
        {LIVE_WEB_SEARCH_CAPABILITY_ID}
    )
    assert runtime.descriptor.capabilities.activity_events is True
