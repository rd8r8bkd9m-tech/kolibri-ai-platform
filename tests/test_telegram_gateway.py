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


def test_plain_text_message_builds_structured_factory_task():
    gateway = load_gateway()
    message = sample_message()
    envelope = gateway.build_task_envelope(message, message["text"], gateway.empty_memory())
    assert envelope["kind"] == "impl_retry_error_clearance"
    assert envelope["target_node"] == "9fts"
    assert envelope["review_node"] == "new"
    assert envelope["create_review_on_complete"] is True
    assert envelope["source"]["message_id"] == 42
    assert "TELEGRAM_BOT_TOKEN" not in envelope


def test_cyrillic_text_keeps_objective_but_uses_ascii_identifiers():
    gateway = load_gateway()
    message = sample_message("Исправь ошибку retry")
    envelope = gateway.build_task_envelope(message, message["text"], gateway.empty_memory())
    assert envelope["objective"] == "Исправь ошибку retry"
    assert envelope["task_id"].isascii()
    assert envelope["branch"].isascii()


def test_task_detection_keeps_chat_questions_live_but_routes_p0_work():
    gateway = load_gateway()
    assert gateway.wants_factory_task("привет") is False
    assert gateway.wants_factory_task("Сколько серверов работает?") is False
    assert gateway.wants_factory_task("телеграм p0") is True
    assert gateway.wants_factory_task("миниапп") is True


def test_director_reply_is_human_and_not_service_dump():
    gateway = load_gateway()
    reply = gateway.build_realtime_owner_reply("Привет", sample_snapshot())
    assert "Привет. Я здесь." in reply
    assert "3 из 3" in reply
    assert "task_id" not in reply.lower()
    assert "artifact" not in reply.lower()
    assert "Понял. Я на связи" not in reply


def test_director_answers_simple_math_and_status():
    gateway = load_gateway()
    assert gateway.build_realtime_owner_reply("2+4", sample_snapshot()) == "2+4 = 6"
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
