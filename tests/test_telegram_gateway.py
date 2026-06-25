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
