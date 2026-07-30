from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import importlib
import json
from pathlib import Path
import sqlite3
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
import pytest

from app.agent_runtime import AgentRuntimeRegistry
from app.config import Settings
from app.main import create_app


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
WEATHER_PROMPT = "Какая погода в Москве?"


def _settings(database_path: Path) -> Settings:
    return replace(
        Settings.for_testing(
            database_url=database_path,
            bootstrap_owner_email=None,
        ),
        direct_model_runtime_enabled=True,
        product_run_poll_seconds=0.05,
    )


def _register(
    client: TestClient,
    *,
    email: str,
) -> tuple[str, str]:
    response = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={
            "email": email,
            "name": email.split("@", 1)[0],
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    csrf = client.cookies.get("kolibri_v3_csrf")
    assert isinstance(csrf, str) and csrf
    tenant_id = response.json()["user"]["tenantId"]
    assert isinstance(tenant_id, str) and tenant_id
    return csrf, tenant_id


def _run_payload() -> dict[str, object]:
    return {
        "threadId": "thread_weather_journey_01",
        "runId": "run_weather_journey_01",
        "state": None,
        "messages": [
            {
                "id": "message_weather_journey_01",
                "role": "user",
                "content": WEATHER_PROMPT,
            }
        ],
        "tools": [],
        "context": [],
        "forwardedProps": {
            "agentProfile": "auto",
            "executionMode": "standard",
            "accessMode": "standard",
        },
    }


def _sse_events(response_text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in response_text.splitlines():
        if not line.startswith("data: "):
            continue
        value = json.loads(line.removeprefix("data: "))
        assert isinstance(value, dict)
        events.append(value)
    return events


def _weather_result() -> dict[str, Any]:
    return {
        "$type": "WeatherWidget",
        "location": "Москва",
        "region": "Москва",
        "country": "Россия",
        "timezone": "Europe/Moscow",
        "observedAt": "2026-07-30T09:15:00+03:00",
        "condition": "Переменная облачность",
        "summary": "Сейчас в Москве: +21 °C, переменная облачность.",
        "weatherCode": 2,
        "temperature": 21.0,
        "feelsLike": 20.4,
        "humidity": 58,
        "windSpeed": 3.2,
        "precipitation": 0.0,
        "isDay": True,
        "forecast": [
            {
                "date": "2026-07-30",
                "condition": "Переменная облачность",
                "weatherCode": 2,
                "temperatureMax": 24.0,
                "temperatureMin": 16.0,
                "precipitationProbability": 10,
            },
            {
                "date": "2026-07-31",
                "condition": "Небольшой дождь",
                "weatherCode": 61,
                "temperatureMax": 22.0,
                "temperatureMin": 15.0,
                "precipitationProbability": 55,
            },
        ],
        "sources": [
            {
                "label": "Provider-neutral weather fixture",
                "sourceUrl": (
                    "https://weather-provider.example.test/"
                    "observations/moscow/2026-07-30"
                ),
            }
        ],
    }


def test_authenticated_weather_journey_is_dated_sourced_durable_and_isolated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove the public weather journey without a model or network dependency."""

    main_module = importlib.import_module("app.main")
    runtime_module = importlib.import_module("app.direct_model_runtime")
    router_module = importlib.import_module("app.chat.router")

    monkeypatch.setattr(
        main_module,
        "build_agent_runtime_registry",
        lambda *_args, **_kwargs: AgentRuntimeRegistry(),
    )

    provider_calls: list[tuple[str, int]] = []

    def deterministic_weather_provider(
        _settings: Settings,
        *,
        location: str,
        forecast_days: int,
    ) -> dict[str, Any]:
        provider_calls.append((location, forecast_days))
        return _weather_result()

    monkeypatch.setattr(
        runtime_module,
        "get_weather",
        deterministic_weather_provider,
    )

    timing: dict[str, float] = {}
    emitted_types: list[str] = []
    original_accept_run = router_module.accept_run
    original_encode_sse = router_module.encode_sse

    def observed_accept_run(*args: Any, **kwargs: Any) -> Any:
        accepted = original_accept_run(*args, **kwargs)
        timing.setdefault("accepted", perf_counter())
        return accepted

    def observed_encode_sse(event: dict[str, Any]) -> str:
        now = perf_counter()
        event_type = str(event.get("type"))
        emitted_types.append(event_type)
        timing.setdefault("first_event", now)
        if event_type == "RUN_FINISHED":
            timing.setdefault("terminal", now)
        return original_encode_sse(event)

    monkeypatch.setattr(router_module, "accept_run", observed_accept_run)
    monkeypatch.setattr(router_module, "encode_sse", observed_encode_sse)

    database_path = tmp_path / "weather-journey.db"
    app = create_app(_settings(database_path))
    with TestClient(app) as client:
        csrf, tenant_id = _register(
            client,
            email="weather-owner@example.com",
        )
        timing["request_started"] = perf_counter()
        response = client.post(
            "/v1/chat/ag-ui",
            headers={
                **ORIGIN,
                "X-CSRF-Token": csrf,
                "Accept": "text/event-stream",
            },
            json=_run_payload(),
        )
        timing["request_completed"] = perf_counter()

        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith(
            "text/event-stream"
        )
        run_id = response.headers["x-kolibri-run-id"]
        events = _sse_events(response.text)
        assert [event["type"] for event in events] == [
            "RUN_STARTED",
            "TOOL_CALL_START",
            "TOOL_CALL_ARGS",
            "TOOL_CALL_END",
            "TOOL_CALL_RESULT",
            "RUN_FINISHED",
        ]
        assert emitted_types == [event["type"] for event in events]
        assert provider_calls == [("Москве", 5)]

        tool_start = events[1]
        tool_args = json.loads(events[2]["delta"])
        tool_result = json.loads(events[4]["content"])
        assert tool_start["toolCallName"] == "get_weather"
        assert tool_args == {"forecastDays": 5, "location": "Москве"}
        assert tool_result["$type"] == "WeatherWidget"
        assert tool_result["location"] == "Москва"
        observed_at = datetime.fromisoformat(tool_result["observedAt"])
        first_forecast_date = datetime.fromisoformat(
            tool_result["forecast"][0]["date"]
        ).date()
        assert observed_at.tzinfo is not None
        assert observed_at.date() == first_forecast_date
        assert tool_result["sources"] == [
            {
                "label": "Provider-neutral weather fixture",
                "sourceUrl": (
                    "https://weather-provider.example.test/"
                    "observations/moscow/2026-07-30"
                ),
            }
        ]
        source_url = urlsplit(tool_result["sources"][0]["sourceUrl"])
        assert source_url.scheme == "https"
        assert source_url.hostname == "weather-provider.example.test"
        assert tool_result["providerLabel"] == "Погодный сервис"
        assert events[-1]["outcome"] == {"type": "success"}
        assert [event["sequence"] for event in events] == list(range(1, 7))

        durable = client.get(
            "/v1/chat/threads/thread_weather_journey_01/messages",
        )
        assert durable.status_code == 200, durable.text
        messages = durable.json()["messages"]
        assert [message["role"] for message in messages] == [
            "user",
            "assistant",
        ]
        stored_tool = messages[1]["content"][0]
        assert stored_tool["type"] == "tool-call"
        assert stored_tool["toolName"] == "get_weather"
        assert stored_tool["args"] == tool_args
        assert stored_tool["result"] == tool_result

        assert (
            timing["request_started"]
            <= timing["accepted"]
            <= timing["first_event"]
            <= timing["terminal"]
            <= timing["request_completed"]
        )
        accept_seconds = timing["accepted"] - timing["request_started"]
        first_event_seconds = (
            timing["first_event"] - timing["request_started"]
        )
        terminal_seconds = timing["terminal"] - timing["request_started"]
        assert accept_seconds < 1.0
        assert first_event_seconds < 1.5
        assert terminal_seconds < 3.0

        database = sqlite3.connect(database_path)
        database.row_factory = sqlite3.Row
        try:
            run_trace = database.execute(
                """
                SELECT status, outcome, last_event_sequence, created_at,
                       finished_at
                FROM chat_runs
                WHERE tenant_id = ? AND id = ?
                LIMIT 1
                """,
                (tenant_id, run_id),
            ).fetchone()
            event_trace = database.execute(
                """
                SELECT sequence, event_type, created_at
                FROM chat_run_events
                WHERE tenant_id = ? AND run_id = ?
                ORDER BY sequence
                """,
                (tenant_id, run_id),
            ).fetchall()
        finally:
            database.close()

        assert run_trace is not None
        assert run_trace["status"] == "succeeded"
        assert run_trace["outcome"] == "success"
        assert run_trace["last_event_sequence"] == len(events)
        assert run_trace["finished_at"] is not None
        assert [row["sequence"] for row in event_trace] == list(range(1, 7))
        assert [row["event_type"] for row in event_trace] == [
            event["type"] for event in events
        ]
        durable_times = [
            datetime.fromisoformat(run_trace["created_at"]),
            *(
                datetime.fromisoformat(row["created_at"])
                for row in event_trace
            ),
            datetime.fromisoformat(run_trace["finished_at"]),
        ]
        assert durable_times == sorted(durable_times)

        trace_evidence = {
            "publicRunId": _run_payload()["runId"],
            "durableRunId": run_id,
            "eventSequence": [row["sequence"] for row in event_trace],
            "acceptMs": round(accept_seconds * 1000, 3),
            "firstEventMs": round(first_event_seconds * 1000, 3),
            "terminalMs": round(terminal_seconds * 1000, 3),
            "httpCompleteMs": round(
                (
                    timing["request_completed"]
                    - timing["request_started"]
                )
                * 1000,
                3,
            ),
            "city": tool_result["location"],
            "observedAt": tool_result["observedAt"],
            "sourceUrl": tool_result["sources"][0]["sourceUrl"],
        }
        logout = client.post(
            "/v1/auth/logout",
            headers={**ORIGIN, "X-CSRF-Token": csrf},
        )
        assert logout.status_code == 200
        _register(client, email="other-weather-tenant@example.com")

        crossed_resume = client.get(
            f"/v1/chat/runs/{run_id}/events",
            headers={"Last-Event-ID": "0"},
        )
        assert crossed_resume.status_code == 404
        assert crossed_resume.json()["code"] == "run_not_found"
        crossed_thread = client.get(
            "/v1/chat/threads/thread_weather_journey_01/messages",
        )
        assert crossed_thread.status_code == 404
        assert crossed_thread.json()["code"] == "thread_not_found"
        print(
            "R1_WEATHER_TRACE="
            + json.dumps(
                trace_evidence,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
