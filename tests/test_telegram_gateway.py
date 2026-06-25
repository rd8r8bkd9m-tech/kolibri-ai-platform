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
    assert envelope["kind"] == "impl_retry_error_clearance"
    assert envelope["target_node"] == "9fts"
    assert envelope["review_node"] == "new"
    assert envelope["create_review_on_complete"] is True
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
    assert envelope["target_node"] == "9fts"
    assert envelope["source"]["message_id"] == 44


def test_plain_language_work_request_creates_factory_task():
    gateway = load_gateway()
    assert gateway.wants_factory_task("Исправь дефект Factory Runtime") is True



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
