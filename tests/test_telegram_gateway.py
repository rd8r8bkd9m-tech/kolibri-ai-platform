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
    assert envelope["kind"] == "orchestrator_chat_response"
    assert envelope["runner"] == "mimo"
    assert envelope["target_node"] == "primary-candidate"
    assert envelope["required_capability"] == "generic_implementation"
    assert "без заготовок" in envelope["objective"]
    assert envelope["source"]["message_id"] == 44


def test_plain_language_work_request_creates_factory_task():
    gateway = load_gateway()
    assert gateway.wants_factory_task("Исправь дефект Factory Runtime") is True


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
    assert envelope["kind"] == "orchestrator_chat_response"
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
        def __init__(self):
            self.envelopes = []
            self.chat_task_id = None

        def create_task(self, envelope):
            self.envelopes.append(envelope)
            if envelope["kind"] == "orchestrator_chat_response":
                self.chat_task_id = envelope["task_id"]
            return {"task_id": envelope["task_id"], "state": "queued"}

        def get_task(self, task_id):
            assert task_id == self.chat_task_id
            return {
                "task_id": task_id,
                "state": "completed",
                "result": {"response": "Принял как P0. Чиню живой Telegram-диалог и верну результат после проверки."},
            }

        def nodes(self):
            return {"nodes": []}

        def get_tasks(self):
            return {"tasks": [], "queue": []}

    telegram = Telegram()
    state = gateway.StateStore(tmp_path / "state.json")
    factory = Factory()
    app = gateway.Gateway(telegram, factory, {100}, state, 1)
    message = {"message_id": 54, "chat": {"id": 100, "type": "private"}, "from": {"id": 100}, "text": "Почини Telegram, он отвечает шаблонами"}
    app.submit_text_task(message, message["text"])
    assert [item["kind"] for item in factory.envelopes] == ["owner_remote_task", "orchestrator_chat_response"]
    assert telegram.messages
    reply = telegram.messages[0][1]
    assert "Telegram" in reply
    for forbidden in ["task_id", "Задача в общем чате", "artifact", "/var/lib"]:
        assert forbidden not in reply


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
    assert factory.envelopes[0]["kind"] == "orchestrator_chat_response"
    assert factory.envelopes[0]["runner"] == "mimo"
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


def test_image_request_builds_owner_image_task():
    gateway = load_gateway()
    message = {
        "message_id": 57,
        "chat": {"id": 100, "type": "private"},
        "from": {"id": 100},
        "text": "Нарисуй логотип Колибри",
    }
    envelope = gateway.build_task_envelope(message, message["text"])
    assert envelope["kind"] == "owner_image_task"
    assert envelope["media_intent"] == "image"
    assert envelope["target_node"] == "primary-candidate"


def test_gateway_sends_image_result_as_photo(tmp_path):
    gateway = load_gateway()

    class Telegram:
        def __init__(self):
            self.photos = []
            self.messages = []

        def send_photo(self, chat_id, photo, caption=None):
            self.photos.append((chat_id, photo, caption))
            return {"message_id": 20}

        def send_message(self, chat_id, text):
            self.messages.append((chat_id, text))

    class Factory:
        pass

    state = gateway.StateStore(tmp_path / "state.json")
    app = gateway.Gateway(Telegram(), Factory(), {100}, state, 1)
    task = {
        "result": {
            "image_path": "/tmp/kolibri.png",
            "response": "Готово, отправляю картинку.\nresult_path: /var/lib/internal",
        }
    }
    assert app.send_result_media(100, task) is True
    assert app.telegram.photos == [(100, "/tmp/kolibri.png", "Готово, отправляю картинку.")]


def test_gateway_remembers_username_for_photo_routing(tmp_path):
    gateway = load_gateway()

    class Telegram:
        pass

    class Factory:
        pass

    state = gateway.StateStore(tmp_path / "state.json")
    app = gateway.Gateway(Telegram(), Factory(), {100}, state, 1)
    message = {
        "message_id": 58,
        "chat": {"id": 100, "type": "private"},
        "from": {"id": 100, "username": "budem16", "first_name": "react"},
    }
    app.remember_chat_identity(message)
    assert app.resolve_chat_ref("@budem16") == 100


def test_owner_image_task_blocker_is_human_readable():
    gateway = load_gateway()
    task = {
        "state": "completed",
        "envelope": {"kind": "owner_image_task"},
        "result": {
            "status": "blocked",
            "response": "Картинку пока не сгенерировал: на удалённом узле не подключен рабочий ключ генерации изображений.",
        },
    }
    message = gateway.format_task_status(task)
    assert "Картинку пока не сгенерировал" in message
    assert "task_id" not in message
