from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app import ai_provider
from app.home_factory_response import (
    HomeFactoryResponseClient,
    HomeFactoryResponseError,
    HomeFactoryResponseSettings,
    _objective,
    factory_response_configuration,
)


ROUTE_DECISION_ID = "route-" + "c" * 32


def _decision(response_id: str, *, execution_mode: str = "fast") -> dict:
    if execution_mode == "mimo":
        selected_route = {
            "runner": "mimo",
            "node_id": "agent04",
            "slot_id": None,
        }
    else:
        selected_route = {
            "runner": "codex",
            "node_id": "home",
            "slot_id": "home-codex-provider",
        }
    return {
        "schema_version": "kolibri.provider-route-decision.v1",
        "authority": "control-plane/home",
        "status": "selected",
        "public_model": "kolibri",
        "decision_id": ROUTE_DECISION_ID,
        "request_binding": {"request_id": response_id},
        "selected_route": selected_route,
    }


def _settings() -> HomeFactoryResponseSettings:
    return HomeFactoryResponseSettings(
        control_plane_url="http://home-control:9101",
        release_id="kolibri-r17-test",
        bearer_token="t" * 48,
        timeout_seconds=10,
        poll_seconds=0.05,
        request_timeout_seconds=2,
    )


def _completed(
    task_id: str,
    *,
    verified: bool = True,
    runner: str = "codex",
) -> dict:
    attempt_id = f"{task_id}-attempt-1"
    binding = "sha256:" + "b" * 64
    result_sha = "sha256:" + "a" * 64
    check_names = [
        "agent",
        "attempt",
        "binding_sha256",
        "fencing_token",
        "node",
        "result",
        "result_reference",
        "result_sha256",
        "status",
        "task",
    ]
    if runner != "mimo":
        check_names.extend(("lease_actor", "lease_slot"))
    checks = {name: True for name in check_names}
    if runner == "mimo":
        node_id = "agent04"
        agent_id = "agent-host-agent04"
        slot_id = None
        model = "mimo/mimo-auto"
    else:
        node_id = "home"
        agent_id = "home-codex-provider"
        slot_id = "home-codex-provider"
        model = "gpt-5.5"
    source = {} if slot_id is None else {"provider_slot_id": slot_id}
    return {
        "task_id": task_id,
        "state": "completed",
        "attempt_id": attempt_id,
        "fencing_token": 1,
        "lease_owner": f"{node_id}:{agent_id}",
        "envelope": {
            "target_node": node_id,
            "runner": runner,
            "source": source,
            "route_decision": {
                "decision_id": ROUTE_DECISION_ID,
                "principal": "principal:portal-owner",
            },
        },
        "result": {
            "status": "completed",
            "response": "Проверенный ответ",
            "model": model,
            "runner": runner,
        },
        "completion_evidence": {
            "node_id": node_id,
            "agent_id": agent_id,
            "attempt_id": attempt_id,
            "fencing_token": 1,
            "result_reference": "/artifacts/result.json",
            "result_sha256": result_sha,
            "binding_sha256": binding,
        },
        "completion_verifier": {
            "verdict": "passed" if verified else "failed",
            "independent": True,
            "verifier": "control-plane/home",
            "binding_sha256": binding,
            "checks": checks,
        },
    }


def test_factory_configuration_requires_safe_token_file_and_redacts_secret(
    tmp_path, monkeypatch
):
    token = "q" * 48
    token_file = tmp_path / "control-plane-token"
    token_file.write_text(token + "\n", encoding="ascii")
    token_file.chmod(0o600)
    monkeypatch.setenv("KOLIBRI_FACTORY_RESPONSES_ENABLED", "1")
    monkeypatch.setenv("KOLIBRI_CONTROL_PLANE_URL", "http://home:9101")
    monkeypatch.setenv("KOLIBRI_CONTROL_PLANE_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("KOLIBRI_RELEASE_ID", "kolibri-test")

    settings = HomeFactoryResponseSettings.from_env()
    public = factory_response_configuration()

    assert settings.bearer_token == token
    assert token not in repr(settings)
    assert public == {
        "configured": True,
        "authority": "home",
        "release_id": "kolibri-test",
        "credential_source": "home_control_plane",
    }
    assert token not in json.dumps(public)


def test_submit_uses_home_control_plane_and_requires_independent_verifier():
    calls: list[tuple[str, str, dict | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer " + "t" * 48
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        if request.url.path == "/v1/runtime/provider-route-decisions":
            return httpx.Response(201, json=_decision(body["request_id"]))
        if request.method == "POST":
            return httpx.Response(201, json={"task_id": body["task_id"], "state": "queued"})
        task_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=_completed(task_id))

    client = HomeFactoryResponseClient(
        _settings(), transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(
        client.submit(
            [{"role": "user", "content": "Привет"}],
            run_id="resp_test",
            idempotency_key="idem-test",
        )
    )

    assert result["content"] == "Проверенный ответ"
    assert result["task_id"] == "KOL-RESP-resp_test"
    assert result["executor_node"] == "home"
    assert result["verifier_node"] == "control-plane/home"
    assert calls[0][0:2] == ("POST", "/v1/runtime/provider-route-decisions")
    assert calls[0][2]["public_model"] == "kolibri"
    assert calls[0][2]["required_capabilities"] == ["chat", "responses"]
    assert calls[1][0:2] == ("POST", "/v1/tasks")
    assert calls[1][2]["target_node"] == "home"
    assert calls[1][2]["runner"] == "codex"
    assert calls[1][2]["required_capability"] == "runner:codex"
    assert "required_capabilities" not in calls[1][2]
    assert calls[1][2]["idempotency_key"] == "idem-test"
    assert calls[1][2]["max_attempts"] == 1
    assert calls[1][2]["fallback_allowed"] is False
    assert calls[1][2]["route_decision_id"] == ROUTE_DECISION_ID
    assert calls[1][2]["source"] == {
        "kind": "kolibri_provider_gateway",
        "control_plane": "home",
        "response_id": "resp_test",
        "identity_contract": "kolibri.public-identity.v1",
        "provider_actor_node_id": "home-codex-provider",
        "provider_slot_id": "home-codex-provider",
    }
    assert calls[2][0:2] == ("GET", "/v1/tasks/KOL-RESP-resp_test")
    assert "t" * 48 not in repr(client.settings)


def test_fast_auto_routing_accepts_verified_mimo_worker_result():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        if request.url.path == "/v1/runtime/provider-route-decisions":
            assert body["execution_mode"] == "fast"
            decision = _decision(body["request_id"])
            decision["selected_route"] = {
                "runner": "mimo",
                "node_id": "agent04",
                "slot_id": None,
            }
            return httpx.Response(201, json=decision)
        if request.method == "POST":
            assert body["target_node"] == "agent04"
            assert body["runner"] == "mimo"
            assert body["required_capability"] == "runner:mimo"
            assert "provider_slot_id" not in body["source"]
            return httpx.Response(201, json={"task_id": body["task_id"], "state": "queued"})
        task_id = request.url.path.rsplit("/", 1)[-1]
        task = _completed(task_id, runner="mimo")
        return httpx.Response(200, json=task)

    result = asyncio.run(HomeFactoryResponseClient(
        _settings(),
        transport=httpx.MockTransport(handler),
    ).submit([{"role": "user", "content": "Привет"}], run_id="mimo-route"))

    assert result["content"] == "Проверенный ответ"
    assert result["runner"] == "mimo"
    assert result["executor_node"] == "agent04"
    assert result["route_decision_id"] == ROUTE_DECISION_ID


def test_factory_objective_is_provider_neutral_and_keeps_role_payload():
    objective = _objective(
        [
            {"role": "system", "content": "Верни JSON-действие"},
            {"role": "user", "content": "Составь смету"},
        ]
    )

    assert "как универсальный AI" not in objective
    assert "Ты — Колибри" not in objective
    assert "внутренний response-only исполнитель" in objective
    assert "не называй внутреннюю модель" in objective
    assert '"role":"system","content":"Верни JSON-действие"' in objective
    assert '"role":"user","content":"Составь смету"' in objective


def test_dedicated_codex_slot_still_requires_slot_specific_verifier_checks():
    task = _completed("KOL-RESP-codex-without-slot-checks")
    task["completion_verifier"]["checks"].pop("lease_actor")
    task["completion_verifier"]["checks"].pop("lease_slot")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        if request.url.path == "/v1/runtime/provider-route-decisions":
            return httpx.Response(201, json=_decision(body["request_id"]))
        if request.method == "POST":
            return httpx.Response(
                201,
                json={"task_id": body["task_id"], "state": "queued"},
            )
        return httpx.Response(200, json=task)

    with pytest.raises(
        HomeFactoryResponseError,
        match="home_factory_completion_unverified",
    ):
        asyncio.run(
            HomeFactoryResponseClient(
                _settings(), transport=httpx.MockTransport(handler)
            ).submit(
                [{"role": "user", "content": "Проверка слота"}],
                run_id="codex-without-slot-checks",
            )
        )


def test_submit_waits_when_completed_result_precedes_verifier():
    polls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        if request.url.path == "/v1/runtime/provider-route-decisions":
            body = json.loads(request.content)
            return httpx.Response(201, json=_decision(body["request_id"]))
        if request.method == "POST":
            body = json.loads(request.content)
            return httpx.Response(
                201, json={"task_id": body["task_id"], "state": "queued"}
            )
        polls += 1
        task = _completed(request.url.path.rsplit("/", 1)[-1])
        if polls == 1:
            task.pop("completion_verifier")
        return httpx.Response(200, json=task)

    client = HomeFactoryResponseClient(
        _settings(), transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(
        client.submit(
            [{"role": "user", "content": "Привет"}],
            run_id="verifier-race",
        )
    )

    assert polls == 2
    assert result["content"] == "Проверенный ответ"
    assert result["task_id"] == "KOL-RESP-verifier-race"


def test_submit_fails_closed_when_completion_is_not_verified():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/runtime/provider-route-decisions":
            body = json.loads(request.content)
            return httpx.Response(201, json=_decision(body["request_id"]))
        if request.method == "POST":
            body = json.loads(request.content)
            return httpx.Response(201, json={"task_id": body["task_id"], "state": "queued"})
        return httpx.Response(200, json=_completed(request.url.path.rsplit("/", 1)[-1], verified=False))

    client = HomeFactoryResponseClient(
        _settings(), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(HomeFactoryResponseError, match="home_factory_completion_unverified"):
        asyncio.run(
            client.submit([{"role": "user", "content": "Привет"}], run_id="bad")
        )


def test_submit_retries_transient_control_plane_timeout_idempotently():
    post_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_attempts
        if request.url.path == "/v1/runtime/provider-route-decisions":
            body = json.loads(request.content)
            return httpx.Response(201, json=_decision(body["request_id"]))
        if request.method == "POST":
            post_attempts += 1
            if post_attempts < 3:
                raise httpx.ReadTimeout("control plane saturated", request=request)
            body = json.loads(request.content)
            return httpx.Response(
                201, json={"task_id": body["task_id"], "state": "queued"}
            )
        return httpx.Response(
            200, json=_completed(request.url.path.rsplit("/", 1)[-1])
        )

    settings = _settings()
    client = HomeFactoryResponseClient(
        HomeFactoryResponseSettings(
            **{
                **settings.__dict__,
                "request_attempts": 3,
                "request_retry_seconds": 0,
            }
        ),
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(
        client.submit(
            [{"role": "user", "content": "Привет"}],
            run_id="retry-saturated-control-plane",
            idempotency_key="retry-saturated-control-plane",
        )
    )

    assert post_attempts == 3
    assert result["task_id"] == "KOL-RESP-retry-saturated-control-plane"


def test_stream_emits_observed_task_lifecycle_then_verified_text_deltas():
    polls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        if request.url.path == "/v1/runtime/provider-route-decisions":
            body = json.loads(request.content)
            return httpx.Response(201, json=_decision(body["request_id"]))
        if request.method == "POST":
            body = json.loads(request.content)
            return httpx.Response(201, json={"task_id": body["task_id"], "state": "queued"})
        polls += 1
        task_id = request.url.path.rsplit("/", 1)[-1]
        if polls == 1:
            return httpx.Response(200, json={
                "task_id": task_id,
                "state": "running",
                "progress": {
                    "schema_version": "kolibri.public-progress.v1",
                    "type": "reasoning_summary_delta",
                    "sequence": 1,
                    "delta": "Проверяю условия запроса",
                },
            })
        return httpx.Response(200, json=_completed(task_id))

    client = HomeFactoryResponseClient(
        _settings(), transport=httpx.MockTransport(handler)
    )

    async def collect():
        return [event async for event in client.stream([{"role": "user", "content": "Привет"}], run_id="stream")]

    events = asyncio.run(collect())
    summaries = [event["work_summary"] for event in events if "work_summary" in event]
    assert summaries == [
        {
            "stage": "provider_route",
            "summary": "Маршрут выполнения выбран",
            "status": "completed",
        },
        {
            "stage": "accepted",
            "summary": "Задача принята фабрикой",
            "status": "completed",
        },
        {
            "stage": "tool_execution",
            "summary": "Исполнитель обрабатывает запрос",
            "status": "active",
        },
        {
            "stage": "reasoning_summary",
            "summary": "Проверяю условия запроса",
            "status": "active",
            "kind": "reasoning_excerpt",
            "step_id": summaries[3]["step_id"],
            "summary_id": summaries[3]["summary_id"],
        },
        {
            "stage": "verification",
            "summary": "Проверка результата завершена",
            "status": "completed",
        },
    ]
    assert all(item["stage"] not in {"factory_dispatch", "factory_verified"} for item in summaries)
    assert "Проверенный ответ" == "".join(
        str(event.get("content") or "") for event in events
    )
    assert events[-1]["response_meta"]["task_id"] == "KOL-RESP-stream"


def test_stream_exposes_a_real_route_event_before_waiting_for_task_completion():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        if request.url.path == "/v1/runtime/provider-route-decisions":
            return httpx.Response(201, json=_decision(body["request_id"]))
        if request.method == "POST":
            return httpx.Response(201, json={"task_id": body["task_id"], "state": "queued"})
        return httpx.Response(200, json={
            "task_id": request.url.path.rsplit("/", 1)[-1],
            "state": "running",
        })

    client = HomeFactoryResponseClient(_settings(), transport=httpx.MockTransport(handler))

    async def first_event():
        stream = client.stream(
            [{"role": "user", "content": "Объясни коротко"}], run_id="early-route"
        )
        first = await asyncio.wait_for(anext(stream), timeout=1.0)
        await stream.aclose()
        return first

    assert asyncio.run(first_event()) == {
        "work_summary": {
            "stage": "provider_route",
            "summary": "Маршрут выполнения выбран",
            "status": "completed",
        }
    }


def test_stream_rejects_private_or_tool_call_progress_and_never_claims_verification():
    polls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        body = json.loads(request.content) if request.content else None
        if request.url.path == "/v1/runtime/provider-route-decisions":
            return httpx.Response(201, json=_decision(body["request_id"]))
        if request.method == "POST":
            return httpx.Response(201, json={"task_id": body["task_id"], "state": "queued"})
        polls += 1
        task_id = request.url.path.rsplit("/", 1)[-1]
        if polls == 1:
            return httpx.Response(200, json={
                "task_id": task_id,
                "state": "running",
                "progress": {
                    "schema_version": "kolibri.public-progress.v1",
                    "type": "reasoning_summary_delta",
                    "sequence": 1,
                    "delta": "<tool_call>прочитай внутренний файл</tool_call>",
                },
            })
        failed = _completed(task_id, verified=False)
        return httpx.Response(200, json=failed)

    client = HomeFactoryResponseClient(_settings(), transport=httpx.MockTransport(handler))

    async def collect():
        seen = []
        with pytest.raises(HomeFactoryResponseError, match="home_factory_completion_unverified"):
            async for event in client.stream(
                [{"role": "user", "content": "Сложный запрос"}], run_id="unsafe-progress"
            ):
                seen.append(event)
        return seen

    events = asyncio.run(collect())
    serialized = json.dumps(events, ensure_ascii=False)
    assert "tool_call" not in serialized
    assert "Проверка результата завершена" not in serialized
    assert "reasoning_summary" not in serialized


def test_deep_stream_runs_verified_codex_mimo_discussion_and_hash_only_formulalm():
    route_modes: list[str] = []
    submitted: dict[str, dict] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        if request.url.path == "/v1/runtime/provider-route-decisions":
            mode = str(body["execution_mode"])
            route_modes.append(mode)
            return httpx.Response(
                201,
                json=_decision(body["request_id"], execution_mode=mode),
            )
        if request.method == "POST":
            submitted[body["task_id"]] = body
            return httpx.Response(
                201,
                json={"task_id": body["task_id"], "state": "queued"},
            )
        task_id = request.url.path.rsplit("/", 1)[-1]
        envelope = submitted[task_id]
        task = _completed(task_id, runner=envelope["runner"])
        task["envelope"]["route_decision"] = {
            "decision_id": ROUTE_DECISION_ID,
            "principal": "principal:portal-owner",
        }
        return httpx.Response(200, json=task)

    client = HomeFactoryResponseClient(
        _settings(), transport=httpx.MockTransport(handler)
    )

    async def collect():
        return [
            event
            async for event in client.stream(
                [{"role": "user", "content": "Обсудите смету"}],
                run_id="deep-stream",
                collaboration=True,
            )
        ]

    events = asyncio.run(collect())
    meta = events[-1]["response_meta"]
    collaboration = meta["collaboration"]
    assert sorted(route_modes) == ["codex", "codex", "mimo"]
    assert {item["role"] for item in collaboration["participants"]} == {
        "codex",
        "mimo",
    }
    assert all(item["verified"] is True for item in collaboration["participants"])
    assert collaboration["reducer"]["verified"] is True
    assert collaboration["formulalm"]["mode"] == "candidate_only"
    assert collaboration["formulalm"]["raw_content_shared"] is False
    assert collaboration["formulalm"]["request_path_training"] is False
    assert collaboration["formulalm"]["automatic_promotion"] is False
    assert "Обсудите смету" not in json.dumps(
        collaboration["formulalm"], ensure_ascii=False
    )
    public_summaries = [
        event["work_summary"]
        for event in events
        if event.get("work_summary")
    ]
    assert public_summaries[-1] == {
        "stage": "response_received",
        "summary": "Проверены результаты участников: 2",
        "status": "completed",
    }
    assert all(item["stage"] != "agent_discussion" for item in public_summaries)


def test_chat_stream_forwards_run_id_to_home_factory_route(monkeypatch):
    provider = {
        "id": "home_factory",
        "model": "kolibri",
        "protocol": "home_factory",
    }
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        ai_provider,
        "_get_providers_for_task",
        lambda _task_type: [provider],
    )

    async def fake_stream(selected, messages, **kwargs):
        assert selected is provider
        captured.update(kwargs)
        yield {"content": "Проверенный ответ", "done": False}
        yield {"content": "", "done": True}

    monkeypatch.setattr(ai_provider, "_stream_ai", fake_stream)

    async def collect():
        return [
            event
            async for event in ai_provider.chat_completion_stream(
                [{"role": "user", "content": "Проверка маршрута"}],
                run_id="resp_correlated",
            )
        ]

    events = asyncio.run(collect())
    assert captured["run_id"] == "resp_correlated"
    assert captured["execution_mode"] == "mimo"
    assert events[-1]["done"] is True


def test_deep_estimate_bypasses_collaboration_and_uses_verified_auto_route(monkeypatch):
    provider = {
        "id": "home_factory",
        "model": "kolibri",
        "protocol": "home_factory",
    }
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        ai_provider,
        "_get_providers_for_task",
        lambda _task_type: [provider],
    )

    async def fake_stream(selected, messages, **kwargs):
        assert selected is provider
        captured.update(kwargs)
        yield {"content": '{"action":"create_estimate"}', "done": False}
        yield {"content": "", "done": True}

    monkeypatch.setattr(ai_provider, "_stream_ai", fake_stream)

    async def collect():
        return [
            event
            async for event in ai_provider.chat_completion_stream(
                [{
                    "role": "user",
                    "content": "Составь готовую смету на одноэтажный дом 123 м²",
                }],
                raw_json_output=True,
                policy={"mode": "deep", "background": True},
                run_id="resp_estimate_single_codex",
            )
        ]

    events = asyncio.run(collect())
    assert captured["execution_mode"] == "fast"
    assert captured["collaboration"] is False
    assert captured["run_id"] == "resp_estimate_single_codex"
    assert events[-1]["done"] is True


def test_deep_general_chat_keeps_verified_collaboration(monkeypatch):
    provider = {
        "id": "home_factory",
        "model": "kolibri",
        "protocol": "home_factory",
    }
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        ai_provider,
        "_get_providers_for_task",
        lambda _task_type: [provider],
    )

    async def fake_stream(selected, messages, **kwargs):
        assert selected is provider
        captured.update(kwargs)
        yield {"content": "Проверенный совместный ответ", "done": False}
        yield {"content": "", "done": True}

    monkeypatch.setattr(ai_provider, "_stream_ai", fake_stream)

    async def collect():
        return [
            event
            async for event in ai_provider.chat_completion_stream(
                [{"role": "user", "content": "Обсудите стратегию проекта"}],
                raw_json_output=True,
                policy={"mode": "deep", "background": True},
                run_id="resp_general_collaboration",
            )
        ]

    events = asyncio.run(collect())
    assert captured["execution_mode"] == "mimo"
    assert captured["collaboration"] is True
    assert events[-1]["done"] is True
