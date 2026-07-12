from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import public_responses_api
from execution_api import ResponseCreate


def _verified_result(text: str) -> dict:
    encoded = text.encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    evidence = [
        {
            "type": "provider_execution",
            "provider": "factory",
            "provider_model": "test-runner",
            "exit_code": 0,
            "output_sha256": digest,
            "output_bytes": len(encoded),
        },
        {
            "type": "deterministic_verifier",
            "verdict": "passed",
            "binding_sha256": "a" * 64,
        },
    ]
    return {
        "response": text,
        "model": "kolibri",
        "technical": {"provider_routing": {"evidence": evidence}},
    }


async def _start_runtime(tmp_path: Path, executor, *, key: str):
    store = public_responses_api.configure_public_response_store(tmp_path / f"{key}.db")
    public_responses_api.configure_public_response_executor(executor)
    session, _ = store.issue("http://testserver", ttl_seconds=900)
    body = ResponseCreate(
        model="kolibri",
        input="stream a verified answer",
        stream=True,
        idempotency_key=key,
    )
    messages = public_responses_api._input_messages(body.input)
    response_id = public_responses_api._opaque_id("resp")
    initial = public_responses_api._response_shell(
        response_id,
        body,
        session["project_id"],
        status="in_progress",
        public_tools=[],
    )
    store.begin_response(
        session,
        response_id=response_id,
        idempotency_key=key,
        request_sha256=public_responses_api._json_hash(
            public_responses_api._request_semantics(body)
        ),
        payload=initial,
        context=messages,
    )
    runtime = await public_responses_api._start_public_response_runtime(
        session=session,
        initial=initial,
        body=body,
        messages=messages,
        requested_tools=[],
        public_tools=[],
    )
    return store, session, runtime


def test_first_event_and_multiple_real_deltas_precede_provider_completion(tmp_path):
    async def scenario():
        provider_waiting = asyncio.Event()
        release_provider = asyncio.Event()
        provider_completed = asyncio.Event()

        async def executor(**kwargs):
            callback = kwargs["stream_callback"]
            callback({"type": "status", "stage": "routing"})
            callback({"type": "text_delta", "delta": "Первая "})
            await asyncio.sleep(0)
            callback({"type": "text_delta", "delta": "часть."})
            provider_waiting.set()
            await release_provider.wait()
            provider_completed.set()
            return _verified_result("Первая часть.")

        store, session, runtime = await _start_runtime(
            tmp_path, executor, key="incremental-before-complete",
        )
        await asyncio.wait_for(provider_waiting.wait(), timeout=1)
        await runtime.drain_provider_events()

        assert provider_completed.is_set() is False
        early = store.list_response_events(
            session["id"], runtime.response_id, after_sequence=-1,
        )
        assert early[0][0] == "response.created"
        early_deltas = [
            payload["delta"]
            for event_type, payload in early
            if event_type == "response.output_text.delta"
        ]
        assert early_deltas == ["Первая ", "часть."]
        assert store.get_response(session["id"], runtime.response_id)[0]["status"] == "in_progress"

        release_provider.set()
        assert runtime.task is not None
        await asyncio.wait_for(runtime.task, timeout=2)
        final = store.get_response(session["id"], runtime.response_id)[0]
        events = store.list_response_events(
            session["id"], runtime.response_id, after_sequence=-1,
        )
        assert final["status"] == "completed"
        assert final["output_text"] == "Первая часть."
        assert "".join(
            payload["delta"]
            for event_type, payload in events
            if event_type == "response.output_text.delta"
        ) == final["output_text"]
        done = next(
            payload for event_type, payload in events
            if event_type == "response.output_text.done"
        )
        assert done["text"] == final["output_text"]
        assert events[-1][0] == "response.completed"

    asyncio.run(scenario())


def test_last_event_id_replay_is_ordered_and_has_no_duplicates(tmp_path):
    async def scenario():
        async def executor(**kwargs):
            kwargs["stream_callback"]({"type": "text_delta", "delta": "A"})
            kwargs["stream_callback"]({"type": "text_delta", "delta": "B"})
            return _verified_result("AB")

        store, session, runtime = await _start_runtime(
            tmp_path, executor, key="durable-replay",
        )
        assert runtime.task is not None
        await asyncio.wait_for(runtime.task, timeout=2)
        all_events = store.list_response_events(
            session["id"], runtime.response_id, after_sequence=-1,
        )
        cursor = all_events[len(all_events) // 2][1]["sequence_number"]
        frames = [
            frame
            async for frame in public_responses_api._stored_response_sse(
                session_id=session["id"],
                response_id=runtime.response_id,
                after_sequence=cursor,
            )
        ]
        replayed = []
        for frame in frames:
            data_line = next(
                line for line in frame.splitlines() if line.startswith("data: ")
            )
            replayed.append(json.loads(data_line.removeprefix("data: ")))
        ids = [item["sequence_number"] for item in replayed]
        expected = [
            payload["sequence_number"]
            for _, payload in all_events
            if payload["sequence_number"] > cursor
        ]
        assert ids == expected
        assert ids == sorted(set(ids))
        assert all(sequence > cursor for sequence in ids)

    asyncio.run(scenario())


def test_stream_disconnect_does_not_cancel_durable_background_runtime(tmp_path):
    async def scenario():
        provider_started = asyncio.Event()
        release_provider = asyncio.Event()

        async def executor(**kwargs):
            kwargs["stream_callback"]({"type": "text_delta", "delta": "still "})
            provider_started.set()
            await release_provider.wait()
            kwargs["stream_callback"]({"type": "text_delta", "delta": "running"})
            return _verified_result("still running")

        store, session, runtime = await _start_runtime(
            tmp_path, executor, key="disconnect-does-not-cancel",
        )
        await asyncio.wait_for(provider_started.wait(), timeout=1)
        stream = public_responses_api._stored_response_sse(
            session_id=session["id"],
            response_id=runtime.response_id,
            after_sequence=-1,
        )
        first_frame = await asyncio.wait_for(anext(stream), timeout=1)
        assert "event: response.created" in first_frame
        await stream.aclose()

        assert runtime.cancel_event.is_set() is False
        assert runtime.task is not None and runtime.task.done() is False

        release_provider.set()
        await asyncio.wait_for(runtime.task, timeout=2)
        final = store.get_response(session["id"], runtime.response_id)[0]
        assert final["status"] == "completed"
        assert final["output_text"] == "still running"
        assert runtime.cancel_event.is_set() is False

    asyncio.run(scenario())


def test_cancel_is_idempotent_and_late_executor_cannot_complete(tmp_path):
    async def scenario():
        provider_started = asyncio.Event()

        async def executor(**kwargs):
            provider_started.set()
            while not kwargs["cancel_event"].is_set():
                await asyncio.sleep(0.01)
            raise asyncio.CancelledError

        store, session, runtime = await _start_runtime(
            tmp_path, executor, key="cancel-idempotent",
        )
        await asyncio.wait_for(provider_started.wait(), timeout=1)
        first = store.cancel_response(session["id"], runtime.response_id)
        runtime.cancel()
        second = store.cancel_response(session["id"], runtime.response_id)
        assert runtime.task is not None
        await asyncio.wait_for(runtime.task, timeout=2)

        assert first == second
        assert first["status"] == "cancelled"
        events = store.list_response_events(
            session["id"], runtime.response_id, after_sequence=-1,
        )
        assert [event_type for event_type, _ in events].count("response.cancelled") == 1
        assert not any(event_type == "response.completed" for event_type, _ in events)
        assert store.get_response(session["id"], runtime.response_id)[0]["status"] == "cancelled"

    asyncio.run(scenario())


def test_removed_public_deadline_copy_is_absent_from_runtime_source():
    forbidden = " ".join((
        "Исполнители не успели завершить ответ",
        "в отведённое время. Повторите запрос.",
    ))
    runtime_roots = (ROOT / "backend", ROOT / "frontend" / "src")
    suffixes = {".py", ".js", ".jsx", ".ts", ".tsx"}
    matches = []
    for runtime_root in runtime_roots:
        for path in runtime_root.rglob("*"):
            if not path.is_file() or path.suffix not in suffixes:
                continue
            if forbidden in path.read_text(encoding="utf-8", errors="ignore"):
                matches.append(str(path.relative_to(ROOT)))
    assert matches == []
