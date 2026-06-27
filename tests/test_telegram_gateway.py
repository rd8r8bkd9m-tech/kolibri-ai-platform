import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_gateway():
    spec = importlib.util.spec_from_file_location("telegram_gateway", ROOT / "ops" / "telegram_gateway.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sample_message(text="Исправь отображение ошибки после успешного retry"):
    return {"message_id": 42, "chat": {"id": 100, "type": "private"}, "from": {"id": 100}, "text": text}


def sample_snapshot():
    return {
        "nodes": [
            {"node_id": "main", "health": "online"},
            {"node_id": "primary-candidate", "health": "online"},
            {"node_id": "9fts", "health": "online"},
        ],
        "active_tasks": [],
        "warnings": [],
        "memory": {"last_work_request": {"text": "телеграм p0", "state": "running"}, "known_results": []},
    }


def test_parse_owner_ids_accepts_commas_and_semicolons():
    gateway = load_gateway()
    assert gateway.parse_owner_ids("1, 2;3") == {1, 2, 3}


def test_plain_text_message_builds_owner_remote_task():
    gateway = load_gateway()
    message = sample_message()
    envelope = gateway.build_task_envelope(message, message["text"], gateway.empty_memory())
    assert envelope["kind"] == "owner_remote_task"
    assert envelope["target_node"] == "primary-candidate"
    assert envelope["required_capability"] == "implementation"
    assert envelope["runner"] == "codex"
    assert envelope["project_path"] == "/var/lib/kolibri-agent/repo"
    assert envelope["source"]["message_id"] == 42
    assert "TELEGRAM_BOT_TOKEN" not in envelope


def test_cyrillic_text_keeps_objective_but_uses_ascii_identifiers():
    gateway = load_gateway()
    message = sample_message("Исправь ошибку retry")
    envelope = gateway.build_task_envelope(message, message["text"], gateway.empty_memory())
    assert envelope["objective"] == "Исправь ошибку retry"
    assert envelope["task_id"].isascii()
    assert "branch" not in envelope
    assert "TGCHAT" not in envelope["task_id"]


def test_task_detection_keeps_chat_questions_live_but_routes_p0_work():
    gateway = load_gateway()
    assert gateway.wants_factory_task("привет") is False
    assert gateway.wants_factory_task("Сколько серверов работает?") is False
    assert gateway.classify_owner_message("почему не получилось?") == "chat"
    assert gateway.classify_owner_message("2+4") == "chat"
    assert gateway.classify_owner_message("почини Telegram") == "task"
    assert gateway.wants_factory_task("телеграм p0") is True
    assert gateway.wants_factory_task("миниапп") is True


def test_director_reply_is_human_and_not_service_dump():
    gateway = load_gateway()
    reply = gateway.build_realtime_owner_reply("Привет", sample_snapshot())
    assert reply == "Привет. Что разбираем?"
    assert "task_id" not in reply.lower()
    assert "artifact" not in reply.lower()
    assert "Понял. Я на связи" not in reply


def test_director_answers_simple_math_and_status():
    gateway = load_gateway()
    assert gateway.build_realtime_owner_reply("2+4", sample_snapshot()) == "6"
    status = gateway.build_realtime_owner_reply("Сколько серверов работает?", sample_snapshot())
    assert "3 из 3" in status


def test_help_text_uses_plain_language_not_service_commands():
    gateway = load_gateway()
    text = gateway.help_text()
    assert "Пишите обычным языком" in text
    assert "/task" not in text
    assert "task_id" not in text.lower()


def test_gateway_source_has_no_old_templates_or_owner_visible_dump():
    source = (ROOT / "ops" / "telegram_gateway.py").read_text(encoding="utf-8")
    assert "Привет. Я на связи. Пиши обычным языком" not in source
    assert "Понял. Я на связи и держу контекст" not in source
    assert "Ответ агента:" not in source
    assert "build_chat_envelope" not in source
    assert "chat_task_id_from_message" not in source


def test_task_transition_cleans_codex_prompt_and_paths_from_agent_response():
    gateway = load_gateway()
    task = {
        "state": "completed",
        "result": {
            "response": (
                "$ /usr/local/bin/codex exec --skip-git-repo-check prompt\n"
                "Ты — удалённый исполнитель фабрики Kolibri.\n"
                "Правила:\n"
                "- не печатай значения секретов\n"
                "Рабочая директория: /var/lib/kolibri-agent/repo\n"
                "task_id: TG-1\n"
                "Готово: Telegram теперь отвечает без служебного мусора."
            ),
            "result_path": "/var/lib/kolibri-agent/artifacts/TG-1/result.json",
        },
    }
    message = gateway.format_transition("COMPLETED", task, mode="task")
    assert message == "Готово: Telegram теперь отвечает без служебного мусора."
    for forbidden in ["codex exec", "prompt", "task_id", "/var/lib", "Рабочая директория", "Правила"]:
        assert forbidden not in message


def test_handle_message_keeps_greeting_and_math_out_of_factory_queue(tmp_path):
    gateway = load_gateway()

    class Telegram:
        def __init__(self):
            self.messages = []

        def send_message(self, chat_id, text):
            self.messages.append((chat_id, text))

    class Factory:
        def create_task(self, envelope):
            raise AssertionError("chat must not enqueue a factory task")

        def nodes(self):
            return {"nodes": []}

        def get_tasks(self):
            return {"tasks": [], "queue": []}

    telegram = Telegram()
    app = gateway.Gateway(telegram, Factory(), {100}, gateway.StateStore(tmp_path / "state.json"), 1)
    app.handle_message({"message_id": 56, "chat": {"id": 100, "type": "private"}, "from": {"id": 100}, "text": "Привет"})
    app.handle_message({"message_id": 57, "chat": {"id": 100, "type": "private"}, "from": {"id": 100}, "text": "2+4"})
    assert telegram.messages[0][1] == "Привет. Что разбираем?"
    assert telegram.messages[1][1] == "6"


def test_handle_message_submits_work_as_owner_remote_task(tmp_path):
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

    factory = Factory()
    telegram = Telegram()
    app = gateway.Gateway(telegram, factory, {100}, gateway.StateStore(tmp_path / "state.json"), 1)
    app.handle_message({"message_id": 58, "chat": {"id": 100, "type": "private"}, "from": {"id": 100}, "text": "почини Telegram"})
    assert factory.envelopes
    envelope = factory.envelopes[0]
    assert envelope["kind"] == "owner_remote_task"
    assert envelope["runner"] == "codex"
    assert envelope["objective"] == "почини Telegram"
    assert "TGCHAT" not in envelope["task_id"]
    assert "Primary Codex" in telegram.messages[0][1]
