from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_gateway():
    spec = importlib.util.spec_from_file_location(
        "telegram_gateway_responses_runtime",
        ROOT / "ops" / "telegram_gateway.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeResponses:
    def __init__(self):
        self.calls = []

    def create_response(self, **request):
        self.calls.append(request)
        number = len(self.calls)
        return {
            "id": f"resp_{number}",
            "status": "completed",
            "output_text": f"Реальный ответ {number}",
        }


class FakeFactory:
    def __init__(self, responses=None):
        self.responses_client = responses

    def nodes(self):
        return {
            "nodes": [
                {
                    "node_id": "worker-a",
                    "health": "online",
                    "freshness": "fresh",
                    "schedulable": True,
                    "capabilities": ["generic_implementation"],
                },
                {
                    "node_id": "worker-b",
                    "health": "offline",
                    "freshness": "stale",
                    "schedulable": False,
                    "capabilities": [],
                },
            ]
        }

    def get_tasks(self):
        return {
            "tasks": [
                {"state": "running", "envelope": {"kind": "build"}},
                {"state": "completed", "envelope": {"kind": "review"}},
            ],
            "queue": ["task-a"],
        }


class FakeTelegram:
    def __init__(self):
        self.messages = []
        self.actions = []
        self.updates = []

    def send_message(self, chat_id, text):
        self.messages.append((chat_id, text))
        return {"message_id": len(self.messages)}

    def send_action(self, chat_id, action="typing"):
        self.actions.append((chat_id, action))

    def get_updates(self, offset, timeout):
        del offset, timeout
        return self.updates


def message(message_id: int, text: str) -> dict:
    return {
        "message_id": message_id,
        "chat": {"id": 100, "type": "private"},
        "from": {"id": 100},
        "text": text,
    }


def test_start_help_and_status_are_distinct_single_useful_replies(tmp_path):
    gateway = load_gateway()
    telegram = FakeTelegram()
    app = gateway.Gateway(
        telegram,
        FakeFactory(FakeResponses()),
        {100},
        gateway.StateStore(tmp_path / "state.json"),
        1,
    )

    app.handle_message(message(1, "/start"))
    app.handle_message(message(2, "/status"))
    app.handle_message(message(3, "/help"))

    assert len(telegram.messages) == 3
    replies = [item[1] for item in telegram.messages]
    assert len(set(replies)) == 3
    assert "Kolibri готов к диалогу" in replies[0]
    assert "живой статус" in replies[1]
    assert "online 1/2" in replies[1]
    assert "активные 1" in replies[1]
    assert "Пишите обычным языком" in replies[2]


def test_normal_prompt_and_ask_use_responses_with_continuity_and_web(tmp_path):
    gateway = load_gateway()
    responses = FakeResponses()
    telegram = FakeTelegram()
    app = gateway.Gateway(
        telegram,
        FakeFactory(responses),
        {100},
        gateway.StateStore(tmp_path / "state.json"),
        1,
    )

    app.handle_message(message(10, "Какие динамики лучше поставить в Hyundai Solaris?"))
    app.handle_message(message(11, "/ask А усилитель к ним какой выбрать?"))

    assert [item[1] for item in telegram.messages] == ["Реальный ответ 1", "Реальный ответ 2"]
    assert responses.calls[0] == {
        "text": "Какие динамики лучше поставить в Hyundai Solaris?",
        "chat_id": 100,
        "message_id": 10,
        "previous_response_id": None,
        "web_search": True,
    }
    assert responses.calls[1]["previous_response_id"] == "resp_1"
    assert responses.calls[1]["web_search"] is True


def test_duplicate_update_is_claimed_before_side_effect_and_replied_once(tmp_path):
    gateway = load_gateway()
    state_path = tmp_path / "state.json"
    state = gateway.StateStore(state_path)
    responses = FakeResponses()

    class PersistenceCheckingTelegram(FakeTelegram):
        def send_message(self, chat_id, text):
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            assert "77" in persisted["processed_updates"]
            assert "100:20" in persisted["processed_messages"]
            return super().send_message(chat_id, text)

    telegram = PersistenceCheckingTelegram()
    repeated = {"update_id": 77, "message": message(20, "привет")}
    telegram.updates = [repeated, repeated]
    app = gateway.Gateway(telegram, FakeFactory(responses), {100}, state, 1)

    app.run_once()

    assert telegram.messages == [(100, "Реальный ответ 1")]
    assert len(responses.calls) == 1
    assert state.data["offset"] == 78


def test_response_failure_is_one_truthful_error_not_canned_success(tmp_path):
    gateway = load_gateway()

    class FailedResponses:
        def create_response(self, **_request):
            raise gateway.ResponsesClientError("provider_unavailable")

    telegram = FakeTelegram()
    app = gateway.Gateway(
        telegram,
        FakeFactory(FailedResponses()),
        {100},
        gateway.StateStore(tmp_path / "state.json"),
        1,
    )

    app.handle_message(message(30, "Привет"))
    app.handle_message(message(30, "Привет"))

    assert len(telegram.messages) == 1
    assert "provider_unavailable" in telegram.messages[0][1]
    assert "Готово" not in telegram.messages[0][1]
    assert "отвечаю сам" not in telegram.messages[0][1]


def test_responses_client_posts_openai_path_with_file_bearer(tmp_path, monkeypatch):
    gateway = load_gateway()
    token_file = tmp_path / "owner-token"
    token_file.write_text("owner-test-token", encoding="utf-8")
    token_file.chmod(0o600)
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({
                "id": "resp_http",
                "status": "completed",
                "output": [{
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Ответ через API"}],
                }],
            }).encode("utf-8")

    class Opener:
        def open(self, request, timeout):
            captured["url"] = request.full_url
            captured["authorization"] = request.headers.get("Authorization")
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return Response()

    monkeypatch.setattr(gateway.urllib.request, "build_opener", lambda *_args: Opener())
    client = gateway.ResponsesClient(
        "http://127.0.0.1:8001",
        token_file,
        timeout=5,
    )

    payload = client.create_response(
        text="Какие динамики лучше?",
        chat_id=100,
        message_id=40,
        web_search=True,
    )

    assert payload["output_text"] == "Ответ через API"
    assert captured["url"] == "http://127.0.0.1:8001/v1/responses"
    assert captured["authorization"] == "Bearer owner-test-token"
    assert captured["body"]["idempotency_key"] == "telegram-response:100:40"
    assert captured["body"]["tools"] == [
        {"type": "web_search", "search_context_size": "medium"}
    ]
