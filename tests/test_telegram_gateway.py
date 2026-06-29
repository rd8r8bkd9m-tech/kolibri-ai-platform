import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_gateway():
    spec = importlib.util.spec_from_file_location("telegram_gateway", ROOT / "ops" / "telegram_gateway.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_owner_ids_accepts_commas_and_semicolons():
    gateway = load_gateway()
    assert gateway.parse_owner_ids("1, 2;3") == {1, 2, 3}


def test_report_sanitizer_redacts_quoted_token_values_and_private_paths():
    gateway = load_gateway()

    safe = gateway.sanitize_report_text(
        "token=\"abc123\"\n"
        "token='def456'\n"
        "password=plain789\n"
        "Authorization: Bearer should-not-leak\n"
        "artifact=/var/lib/kolibri-agent/worktrees/task/result.json\n"
        "secret_file=/run/secrets/telegram.env\n"
        "config=/etc/kolibri/telegram.env\n"
        "tmp=/tmp/private.log\n"
    )

    for leaked in [
        "abc123",
        "def456",
        "plain789",
        "should-not-leak",
        "/var/lib/kolibri-agent",
        "/run/secrets",
        "/etc/kolibri",
        "/tmp/private.log",
    ]:
        assert leaked not in safe
    assert "token=\"[скрыто]\"" in safe
    assert "token='[скрыто]'" in safe
    assert "password=[скрыто]" in safe
    assert "[строка скрыта: секретный материал]" in safe
    assert safe.count("[внутренний путь скрыт]") == 4


def test_report_letter_has_document_headers_and_sanitized_body(tmp_path, monkeypatch):
    gateway = load_gateway()
    monkeypatch.setattr(gateway, "utc_now", lambda: "2026-06-29T12:00:00+00:00")
    report = tmp_path / "factory-status.md"
    report.write_text("# Отчёт\n\nГотово.\nsecret=hidden-value\npath=/tmp/private.log\n", encoding="utf-8")

    letter = gateway.build_report_letter(
        report,
        title="Статус фабрики",
        agent="Супервизор",
        status="blocked",
        summary="token='summary-secret'",
    )

    assert "Тема: Статус фабрики" in letter
    assert "Дата: 2026-06-29T12:00:00+00:00" in letter
    assert "Ответственный: Супервизор" in letter
    assert "Статус: blocked" in letter
    assert "Кратко:" in letter
    assert "Документ:" in letter
    assert "hidden-value" not in letter
    assert "summary-secret" not in letter
    assert "/tmp/private.log" not in letter


def test_split_telegram_text_keeps_parts_under_limit_without_empty_chunks():
    gateway = load_gateway()
    parts = gateway.split_telegram_text("A" * 15 + "\n\n" + "B" * 37, limit=20)

    assert len(parts) == 3
    assert all(parts)
    assert all(len(part) <= 20 for part in parts)
    assert "".join(parts).replace("\n", "") == ("A" * 15) + ("B" * 37)


def test_send_report_letter_requires_owner_chat_id(tmp_path):
    gateway = load_gateway()
    report = tmp_path / "status.md"
    report.write_text("Готово", encoding="utf-8")
    state = gateway.StateStore(tmp_path / "state.json")

    class Telegram:
        def __init__(self):
            self.calls = []

        def send_text_document(self, chat_id, title, text):
            self.calls.append((chat_id, title, text))
            return 1

    telegram = Telegram()
    try:
        gateway.send_report_letter(telegram, state, report)
    except RuntimeError as exc:
        assert "owner chat id" in str(exc)
    else:
        raise AssertionError("send_report_letter accepted missing owner chat id")
    assert telegram.calls == []


def test_send_report_letter_uses_state_owner_chat_id(tmp_path):
    gateway = load_gateway()
    report = tmp_path / "status.md"
    report.write_text("Готово", encoding="utf-8")
    state = gateway.StateStore(tmp_path / "state.json")
    state.data["owner_chat_id"] = 100

    class Telegram:
        def __init__(self):
            self.calls = []

        def send_text_document(self, chat_id, title, text):
            self.calls.append((chat_id, title, text))
            return 1

    telegram = Telegram()
    result = gateway.send_report_letter(telegram, state, report, title="Письмо", agent="Агент", status="готово")

    assert result == {"chat_id": 100, "parts": 1, "title": "Письмо"}
    assert telegram.calls
    assert telegram.calls[0][0] == 100
    assert "Тема: Письмо" in telegram.calls[0][2]


def test_report_cli_send_report_does_not_require_owner_ids(tmp_path, monkeypatch, capsys):
    gateway = load_gateway()
    report = tmp_path / "status.md"
    state_file = tmp_path / "state.json"
    report.write_text("Готово\nsecret=hidden\n", encoding="utf-8")
    sent = []

    class Telegram:
        def __init__(self, token):
            assert token == "fake-token"

        def send_text_document(self, chat_id, title, text):
            sent.append((chat_id, title, text))
            return 1

    monkeypatch.setattr(gateway, "TelegramClient", Telegram)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.delenv("TELEGRAM_OWNER_IDS", raising=False)
    monkeypatch.setattr(
        gateway.sys,
        "argv",
        [
            "telegram_gateway.py",
            "--state-file",
            str(state_file),
            "--send-report",
            str(report),
            "--report-chat-id",
            "100",
            "--report-title",
            "Письмо",
        ],
    )

    assert gateway.main() == 0
    output = capsys.readouterr().out
    assert '"event": "telegram_report_sent"' in output
    assert '"chat_id": 100' in output
    assert "hidden" not in output
    assert sent
    assert sent[0][0] == 100
    assert sent[0][1] == "Письмо"
    assert "secret=[скрыто]" in sent[0][2]


def test_factory_client_fails_over_between_control_plane_urls(monkeypatch):
    gateway = load_gateway()
    calls = []

    def fake_request(method, url, body=None, timeout=35):
        calls.append((method, url, body, timeout))
        if url.startswith("http://down"):
            raise RuntimeError("down")
        return {"status": "ok"}

    monkeypatch.setattr(gateway, "json_request", fake_request)
    client = gateway.FactoryClient("http://down:9101", "http://down:9101,http://alive:9101")
    assert client.nodes() == {"status": "ok"}
    assert calls[0][1] == "http://down:9101/v1/nodes"
    assert calls[1][1] == "http://alive:9101/v1/nodes"
    assert client.control_url == "http://alive:9101"
    client.get_tasks()
    assert calls[-1][1] == "http://alive:9101/v1/tasks"


def test_plain_text_message_builds_structured_factory_task():
    gateway = load_gateway()
    message = {
        "message_id": 42,
        "chat": {"id": 100, "type": "private"},
        "from": {"id": 100},
        "text": "Исправь отображение ошибки после успешного retry",
    }
    envelope = gateway.build_task_envelope(message, message["text"])
    assert envelope["kind"] == "owner_remote_task"
    assert "target_node" not in envelope
    assert envelope["required_capability"] == "generic_implementation"
    assert envelope["review_node"] == "new"
    assert envelope["create_review_on_complete"] is False
    assert envelope["source"]["message_id"] == 42
    assert "TELEGRAM_BOT_TOKEN" not in envelope


def test_cyrillic_text_keeps_objective_but_uses_ascii_identifiers():
    gateway = load_gateway()
    message = {
        "message_id": 43,
        "chat": {"id": 100, "type": "private"},
        "from": {"id": 100},
        "text": "Исправь ошибку retry",
    }
    envelope = gateway.build_task_envelope(message, message["text"])
    assert envelope["objective"] == "Исправь ошибку retry"
    assert envelope["task_id"].isascii()
    assert envelope["branch"].isascii()


def test_greeting_is_chat_not_factory_task():
    gateway = load_gateway()
    assert gateway.wants_factory_task("привет") is False
    message = {
        "message_id": 44,
        "chat": {"id": 100, "type": "private"},
        "from": {"id": 100},
        "text": "привет",
    }
    envelope = gateway.build_chat_envelope(message, message["text"])
    assert envelope["kind"] == "owner_remote_task"
    assert envelope["runner"] == "codex"
    assert envelope["target_node"] == "primary-candidate"
    assert envelope["required_capability"] == "generic_implementation"
    assert "без заготовок" in envelope["objective"]
    assert envelope["source"]["message_id"] == 44


def test_plain_language_work_request_creates_factory_task():
    gateway = load_gateway()
    assert gateway.wants_factory_task("Исправь дефект Factory Runtime") is True
    assert gateway.wants_factory_task("телеграм p0") is True
    assert gateway.wants_factory_task("миниапп") is True
    assert gateway.wants_factory_task("Сколько серверов работает?") is False


def test_image_request_builds_telegram_image_task():
    gateway = load_gateway()
    message = {
        "message_id": 58,
        "chat": {"id": 100, "type": "private"},
        "from": {"id": 100},
        "text": "Нарисуй живую птичку Колибри",
    }
    assert gateway.wants_image_generation(message["text"]) is True
    envelope = gateway.build_image_envelope(message, message["text"], {"nodes": []})
    assert envelope["kind"] == "telegram_image_generation"
    assert envelope["required_capability"] == "generic_implementation"
    assert envelope["target_node"] == "primary-candidate"
    assert envelope["message"] == message["text"]
    assert envelope["prompt"] == message["text"]
    assert envelope["task_id"].startswith("TGIMG-")
    assert "image_url" in envelope["objective"]


def test_explicit_telegram_node_env_pins_task(monkeypatch):
    gateway = load_gateway()
    monkeypatch.setenv("TELEGRAM_TASK_NODE", "primary-candidate")
    monkeypatch.setenv("TELEGRAM_CHAT_NODE", "primary-candidate")
    message = {
        "message_id": 444,
        "chat": {"id": 100, "type": "private"},
        "from": {"id": 100},
        "text": "Исправь Telegram",
    }
    assert gateway.build_task_envelope(message, message["text"])["target_node"] == "primary-candidate"
    assert gateway.build_chat_envelope(message, "как дела?")["target_node"] == "primary-candidate"



def test_chat_transition_hides_factory_metadata():
    gateway = load_gateway()
    task = {
        "task_id": "TGCHAT-20260625132639-4037-task",
        "state": "completed",
        "result": {
            "node_id": "9fts",
            "agent_id": "agent-host-9fts",
            "result_path": "/var/lib/kolibri-agent/artifacts/TGCHAT/result.json",
            "response": "Привет! 👋 Чем могу помочь?\nnode: 9fts\nagent: agent-host-9fts\nartifact: /var/lib/kolibri-agent/result.json",
        },
    }
    message = gateway.format_transition("COMPLETED", task, mode="chat")
    assert message == "Привет! Чем могу помочь?"
    for forbidden in ["task_id", "node:", "agent:", "artifact:", "/var/lib", "TGCHAT"]:
        assert forbidden not in message


def test_task_transition_is_human_readable_without_internal_metadata():
    gateway = load_gateway()
    task = {
        "task_id": "TG-20260625140000-1-task",
        "state": "completed",
        "result": {
            "node_id": "9fts",
            "agent_id": "agent-host-9fts",
            "result_path": "/var/lib/kolibri-agent/artifacts/TG/result.json",
        },
    }
    message = gateway.format_transition("COMPLETED", task, mode="task")
    assert "Готово" in message
    for forbidden in ["task_id", "node:", "agent:", "artifact:", "/var/lib", "TG-202606"]:
        assert forbidden not in message


def test_owner_remote_task_completion_returns_clean_url_result():
    gateway = load_gateway()
    task = {
        "state": "completed",
        "envelope": {"kind": "owner_remote_task"},
        "result": {
            "response": (
                "Проект запущен.\n"
                "Frontend: `http://178.207.11.90:8180`\n"
                "Backend API: `http://178.207.11.90:8000/docs`\n"
                "Секреты: JWT_SECRET_KEY и TELEGRAM_BOT_TOKEN доступны.\n"
                "result_path: /var/lib/kolibri-agent/result.json\n"
                "PostgreSQL Healthy"
            )
        },
    }
    message = gateway.format_task_status(task)
    assert "http://178.207.11.90:8180" in message
    assert "http://178.207.11.90:8000/docs" in message
    assert "Проверки живые" in message
    for forbidden in ["SECRET", "TOKEN", "result_path", "/var/lib"]:
        assert forbidden not in message


def test_gateway_auto_tracks_fresh_owner_tasks_for_common_chat(tmp_path):
    gateway = load_gateway()

    class Telegram:
        def send_message(self, chat_id, text):
            pass

    class Factory:
        def get_tasks(self):
            return {
                "tasks": [
                    {
                        "task_id": "KOL-OWNER-1",
                        "state": "running",
                        "created_at": "2026-06-27T09:10:54+00:00",
                        "envelope": {"kind": "owner_remote_task"},
                    }
                ]
            }

    state = gateway.StateStore(tmp_path / "state.json")
    state.data["owner_chat_id"] = 100
    state.data["common_chat_since"] = "2026-06-27T09:00:00+00:00"
    app = gateway.Gateway(Telegram(), Factory(), {100}, state, 1)
    app.auto_track_owner_tasks()
    assert state.data["tracked"]["KOL-OWNER-1"]["chat_id"] == 100
    assert state.data["tracked"]["KOL-OWNER-1"]["last_state"] == "WATCHING"


def test_orchestrator_chat_envelope_carries_factory_snapshot():
    gateway = load_gateway()
    message = {
        "message_id": 45,
        "chat": {"id": 100, "type": "private"},
        "from": {"id": 100},
        "text": "фабрика уже работает?",
    }
    snapshot = {"nodes": [{"node_id": "9fts", "health": "online"}], "task_counts": {"completed": 3}}
    envelope = gateway.build_chat_envelope(message, message["text"], snapshot)
    assert envelope["kind"] == "owner_remote_task"
    assert envelope["factory_snapshot"] == snapshot
    assert envelope["message"] == "фабрика уже работает?"
    assert "фабрика уже работает?" in envelope["objective"]


def test_compact_factory_snapshot_has_director_and_team_cards():
    gateway = load_gateway()

    class Factory:
        def nodes(self):
            return {"nodes": [{"node_id": "9fts", "health": "online", "capabilities": ["implementation"]}]}

        def get_tasks(self):
            return {"tasks": [{"state": "running", "envelope": {"target_node": "9fts"}}], "queue": ["one"]}

    snapshot = gateway.compact_factory_snapshot(Factory())
    assert snapshot["orchestrator"]["name"] == "Директор"
    assert snapshot["team"][0]["name"] == "Инженер"
    assert snapshot["queue_length"] == 1
    assert snapshot["task_counts"]["running"] == 1



def test_chat_transition_polishes_brand_typo():
    gateway = load_gateway()
    task = {
        "state": "completed",
        "result": {"response": "Привет! 👋 Я Kolibi, ваш оркестратор.\nnode: 9fts"},
    }
    message = gateway.format_transition("COMPLETED", task, mode="chat")
    assert message == "Привет! Я Kolibri, ваш оркестратор."
    assert "node:" not in message



def test_state_store_initializes_persistent_memory(tmp_path):
    gateway = load_gateway()
    store = gateway.StateStore(tmp_path / "state.json")
    assert store.data["memory"]["project"]["owner_interface"].startswith("Владелец пишет")
    assert store.data["memory"]["recent_messages"] == []


def test_owner_followup_memory_remembers_webapp_link_context():
    gateway = load_gateway()
    memory = gateway.empty_memory()
    gateway.record_owner_message(memory, "Запусти вебприложение", "task", "2026-06-25T14:00:00+00:00")
    gateway.record_work_task(memory, "Запусти вебприложение", "TG-1", "queued", "2026-06-25T14:00:01+00:00")
    gateway.record_owner_message(memory, "Ссылку не забудь прислать", "chat", "2026-06-25T14:01:00+00:00")
    snapshot = gateway.memory_snapshot(memory)
    assert snapshot["last_work_request"]["text"] == "Запусти вебприложение"
    expectation_text = " ".join(item["text"] for item in snapshot["open_expectations"])
    assert "ссыл" in expectation_text
    assert "preview" in expectation_text


def test_chat_envelope_carries_development_memory_snapshot():
    gateway = load_gateway()
    message = {
        "message_id": 46,
        "chat": {"id": 100, "type": "private"},
        "from": {"id": 100},
        "text": "ссылку не забудь",
    }
    snapshot = {
        "memory": {
            "last_work_request": {"text": "Запусти вебприложение", "state": "queued"},
            "recent_messages": [{"role": "owner", "text": "Запусти вебприложение"}],
            "open_expectations": [{"kind": "link", "text": "не забыть прислать ссылку"}],
        }
    }
    envelope = gateway.build_chat_envelope(message, message["text"], snapshot)
    assert envelope["factory_snapshot"]["memory"]["last_work_request"]["text"] == "Запусти вебприложение"
    assert envelope["factory_snapshot"]["memory"]["open_expectations"][0]["kind"] == "link"


def test_work_task_envelope_carries_conversation_context():
    gateway = load_gateway()
    message = {
        "message_id": 47,
        "chat": {"id": 100, "type": "private"},
        "from": {"id": 100},
        "text": "Запусти вебприложение",
    }
    context = {"memory": {"recent_messages": [{"role": "owner", "text": "Запусти вебприложение"}]}}
    envelope = gateway.build_task_envelope(message, message["text"], context)
    assert envelope["conversation_context"] == context


def test_kimi_owner_task_points_to_remote_project_path():
    gateway = load_gateway()
    message = {
        "message_id": 48,
        "chat": {"id": 100, "type": "private"},
        "from": {"id": 100},
        "text": "Перенеси Kimi_Agent_КолибриФин и запусти dev сервер",
    }
    envelope = gateway.build_task_envelope(message, message["text"])
    assert envelope["kind"] == "owner_remote_task"
    assert envelope["project_path"] == "/home/ladik/kolibri-projects/kimi_agent_kolibrifin"



def test_realtime_reply_links_followup_to_last_work_request():
    gateway = load_gateway()
    memory = gateway.empty_memory()
    gateway.record_work_task(memory, "Запусти вебприложение", "TG-1", "queued", "2026-06-25T14:00:01+00:00")
    reply = gateway.build_realtime_owner_reply("Ссылку не забудь прислать", {"memory": gateway.memory_snapshot(memory)})
    assert "Запусти вебприложение" in reply
    assert "Ссылку пришлю" in reply
    assert "уточ" not in reply.lower()


def test_realtime_status_reply_uses_factory_context():
    gateway = load_gateway()
    memory = gateway.empty_memory()
    gateway.record_work_task(memory, "Запусти вебприложение", "TG-1", "running", "2026-06-25T14:00:01+00:00")
    snapshot = {
        "memory": gateway.memory_snapshot(memory),
        "queue_length": 1,
        "active_tasks": [{"state": "running", "kind": "deploy"}],
        "team": [{"name": "Инженер", "health": "online"}, {"name": "Ревьюер", "health": "online"}],
    }
    reply = gateway.build_realtime_owner_reply("Какие задачи выполняешь?", snapshot)
    assert "Сейчас в работе 1 задач" in reply
    assert "Очередь" not in reply
    assert "Инженер" in reply
    assert "Запусти вебприложение" in reply


def test_realtime_dev_server_question_returns_ready_preview_url():
    gateway = load_gateway()
    memory = gateway.empty_memory()
    gateway.record_work_task(memory, "Запустить веб-приложение/dev server", "TG-1", "completed", "2026-06-25T14:00:01+00:00")
    memory["known_results"].append({"kind": "preview_url", "url": "http://104.253.43.117/_kolibri_preview_/"})
    snapshot = {
        "memory": gateway.memory_snapshot(memory),
        "active_tasks": [],
        "team": [{"name": "Инженер", "health": "online"}, {"name": "Ревьюер", "health": "online"}],
    }
    reply = gateway.build_realtime_owner_reply("Дев сервер запущен?", snapshot)
    assert reply == "Да, запущено. Веб-приложение доступно здесь: http://104.253.43.117/_kolibri_preview_/"
    for forbidden in ["task_id", "node:", "agent:", "artifact:", "Очередь", "/var/lib"]:
        assert forbidden not in reply


def test_realtime_reply_answers_simple_arithmetic():
    gateway = load_gateway()
    reply = gateway.build_realtime_owner_reply("2+4", {"memory": gateway.memory_snapshot(gateway.empty_memory())})
    assert reply == "6"


def test_submit_text_task_ack_is_human_without_service_template(tmp_path):
    gateway = load_gateway()

    class Telegram:
        def __init__(self):
            self.messages = []

        def send_message(self, chat_id, text):
            self.messages.append((chat_id, text))

    class Factory:
        def create_task(self, envelope):
            return {"task_id": envelope["task_id"], "state": "queued"}

        def nodes(self):
            return {"nodes": []}

        def get_tasks(self):
            return {"tasks": [], "queue": []}

    telegram = Telegram()
    state = gateway.StateStore(tmp_path / "state.json")
    app = gateway.Gateway(telegram, Factory(), {100}, state, 1)
    message = {"message_id": 54, "chat": {"id": 100, "type": "private"}, "from": {"id": 100}, "text": "Почини Telegram, он отвечает шаблонами"}
    app.submit_text_task(message, message["text"])
    assert telegram.messages
    reply = telegram.messages[0][1]
    assert "главный баг" in reply
    for forbidden in ["task_id", "Задача в общем чате", "artifact", "/var/lib"]:
        assert forbidden not in reply


def test_help_text_uses_plain_language_not_service_commands():
    gateway = load_gateway()
    text = gateway.help_text()
    assert "Пишите обычным языком" in text
    assert "/task" not in text
    assert "task_id" not in text.lower()


def test_submit_text_task_control_plane_failure_is_human(tmp_path):
    gateway = load_gateway()

    class Telegram:
        def __init__(self):
            self.messages = []

        def send_message(self, chat_id, text):
            self.messages.append((chat_id, text))

    class Factory:
        def create_task(self, envelope):
            raise RuntimeError("control plane down")

        def nodes(self):
            return {"nodes": []}

        def get_tasks(self):
            return {"tasks": [], "queue": []}

    telegram = Telegram()
    state = gateway.StateStore(tmp_path / "state.json")
    app = gateway.Gateway(telegram, Factory(), {100}, state, 1)
    message = {"message_id": 57, "chat": {"id": 100, "type": "private"}, "from": {"id": 100}, "text": "телеграм p0"}
    app.submit_text_task(message, message["text"])
    assert telegram.messages == [(100, "Я услышал задачу, но Control Plane сейчас не принял её в очередь. Зафиксировал сбой и разбираю отдельно.")]
    assert state.data["memory"]["last_work_request"]["state"] == "failed"


def test_submit_image_task_queues_remote_generation(tmp_path):
    gateway = load_gateway()

    class Telegram:
        def __init__(self):
            self.messages = []

        def send_message(self, chat_id, text):
            self.messages.append((chat_id, text))

    class Factory:
        def __init__(self):
            self.envelopes = []

        def create_task(self, envelope):
            self.envelopes.append(envelope)
            return {"task_id": envelope["task_id"], "state": "queued"}

        def nodes(self):
            return {"nodes": []}

        def get_tasks(self):
            return {"tasks": [], "queue": []}

    telegram = Telegram()
    factory = Factory()
    state = gateway.StateStore(tmp_path / "state.json")
    app = gateway.Gateway(telegram, factory, {100}, state, 1)
    message = {"message_id": 59, "chat": {"id": 100, "type": "private"}, "from": {"id": 100}, "text": "Сгенерируй картинку премиального миниаппа"}
    app.submit_image_task(message, message["text"])
    assert factory.envelopes[0]["kind"] == "telegram_image_generation"
    assert state.data["tracked"][factory.envelopes[0]["task_id"]]["mode"] == "image"
    assert telegram.messages == [(100, "Принял. Запускаю генерацию изображения и пришлю сюда готовую картинку.")]


def test_image_task_completion_sends_photo_and_cleans_caption(tmp_path):
    gateway = load_gateway()
    tiny_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="

    class Telegram:
        def __init__(self):
            self.messages = []
            self.photos = []

        def send_message(self, chat_id, text):
            self.messages.append((chat_id, text))

        def send_photo(self, chat_id, photo, caption=None, mime_type=None):
            self.photos.append((chat_id, photo, caption, mime_type))

    class Factory:
        def __init__(self, task):
            self.task = task

        def get_tasks(self):
            return {"tasks": [], "queue": []}

        def get_task(self, task_id):
            assert task_id == self.task["task_id"]
            return self.task

    task = {
        "task_id": "TGIMG-202606280001-59-image",
        "state": "completed",
        "envelope": {"kind": "telegram_image_generation"},
        "result": {
            "image_b64": tiny_png_b64,
            "image_mime_type": "image/png",
            "caption": "Готово.\nnode: primary-candidate\nartifact: /var/lib/kolibri-agent/image.png",
        },
    }
    telegram = Telegram()
    state = gateway.StateStore(tmp_path / "state.json")
    state.data["owner_chat_id"] = 100
    state.data["tracked"][task["task_id"]] = {"chat_id": 100, "last_state": "RUNNING", "mode": "image"}
    app = gateway.Gateway(telegram, Factory(task), {100}, state, 1)
    app.poll_task_transitions()
    assert len(telegram.photos) == 1
    chat_id, photo, caption, mime_type = telegram.photos[0]
    assert chat_id == 100
    assert isinstance(photo, bytes)
    assert caption == "Готово."
    assert mime_type == "image/png"
    assert telegram.messages == []
    assert task["task_id"] not in state.data["tracked"]


def test_submit_chat_task_uses_remote_orchestrator_and_hides_intermediate_states(tmp_path, monkeypatch):
    gateway = load_gateway()
    monkeypatch.setenv("TELEGRAM_CHAT_WAIT_SECONDS", "2")

    class Telegram:
        def __init__(self):
            self.messages = []
            self.actions = []

        def send_message(self, chat_id, text):
            self.messages.append((chat_id, text))

        def send_action(self, chat_id, action="typing"):
            self.actions.append((chat_id, action))

    class Factory:
        def __init__(self):
            self.envelopes = []
            self.task_id = None

        def create_task(self, envelope):
            self.envelopes.append(envelope)
            self.task_id = envelope["task_id"]
            return {"task_id": self.task_id, "state": "queued"}

        def get_task(self, task_id):
            assert task_id == self.task_id
            return {
                "task_id": task_id,
                "state": "completed",
                "result": {
                    "response": "Смотрю состояние фабрики.\nnode: home-live\nworktree: /var/lib/kolibri-agent/repo"
                },
            }

        def nodes(self):
            return {"nodes": [{"node_id": "home-live", "health": "online", "capabilities": ["generic_implementation"]}]}

        def get_tasks(self):
            return {"tasks": [], "queue": []}

    telegram = Telegram()
    factory = Factory()
    state = gateway.StateStore(tmp_path / "state.json")
    app = gateway.Gateway(telegram, factory, {100}, state, 1)
    message = {"message_id": 55, "chat": {"id": 100, "type": "private"}, "from": {"id": 100}, "text": "Что выполняешь?"}
    app.submit_chat_task(message, message["text"])
    assert factory.envelopes
    assert factory.envelopes[0]["kind"] == "owner_remote_task"
    assert factory.envelopes[0]["runner"] == "codex"
    assert factory.envelopes[0]["target_node"] == "primary-candidate"
    assert telegram.actions == [(100, "typing")]
    assert telegram.messages
    assert telegram.messages[0][1] == "Смотрю состояние фабрики."
    assert state.data["memory"]["recent_messages"][-1]["role"] == "orchestrator"


def test_submit_chat_task_streams_partial_response_with_edit(tmp_path, monkeypatch):
    gateway = load_gateway()
    monkeypatch.setenv("TELEGRAM_CHAT_WAIT_SECONDS", "4")
    monkeypatch.setenv("TELEGRAM_CHAT_FIRST_REPLY_SECONDS", "0")

    class Telegram:
        def __init__(self):
            self.messages = []
            self.edits = []
            self.actions = []
            self.next_message_id = 10

        def send_message(self, chat_id, text):
            self.messages.append((chat_id, text))
            self.next_message_id += 1
            return {"message_id": self.next_message_id}

        def edit_message(self, chat_id, message_id, text):
            self.edits.append((chat_id, message_id, text))
            return {"message_id": message_id}

        def send_action(self, chat_id, action="typing"):
            self.actions.append((chat_id, action))

    class Factory:
        def __init__(self):
            self.task_id = None
            self.calls = 0

        def create_task(self, envelope):
            self.task_id = envelope["task_id"]
            return {"task_id": self.task_id, "state": "queued"}

        def get_task(self, task_id):
            assert task_id == self.task_id
            self.calls += 1
            if self.calls == 1:
                return {"task_id": task_id, "state": "running", "result": {"partial_response": "Думаю над ответом."}}
            return {"task_id": task_id, "state": "completed", "result": {"response": "Ответ готов.\nnode: home"}}

        def nodes(self):
            return {"nodes": []}

        def get_tasks(self):
            return {"tasks": [], "queue": []}

    telegram = Telegram()
    state = gateway.StateStore(tmp_path / "state.json")
    app = gateway.Gateway(telegram, Factory(), {100}, state, 1)
    message = {"message_id": 56, "chat": {"id": 100, "type": "private"}, "from": {"id": 100}, "text": "Что происходит?"}
    app.submit_chat_task(message, message["text"])

    assert telegram.messages == [(100, "Думаю над ответом.")]
    assert telegram.edits == [(100, 11, "Ответ готов.")]
