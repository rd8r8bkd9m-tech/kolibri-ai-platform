import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_gateway():
    spec = importlib.util.spec_from_file_location("telegram_gateway", ROOT / "ops" / "telegram_gateway.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_webhook_migration():
    spec = importlib.util.spec_from_file_location("telegram_webhook_migration", ROOT / "ops" / "telegram_webhook_migration.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_owner_ids_accepts_commas_and_semicolons():
    gateway = load_gateway()
    assert gateway.parse_owner_ids("1, 2;3") == {1, 2, 3}


def test_default_telegram_client_blocks_delivery_state_mutation(monkeypatch):
    gateway = load_gateway()

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("default client must not call Telegram for blocked delivery-state mutations")

    monkeypatch.setattr(gateway.urllib.request, "urlopen", fail_urlopen)
    client = gateway.TelegramClient("fake-token")
    for method in gateway.DELIVERY_STATE_MUTATION_METHODS:
        try:
            client.call(method)
        except RuntimeError as exc:
            assert method in str(exc)
        else:
            raise AssertionError(f"{method} was not blocked")


def test_default_gateway_startup_is_non_mutating_with_unsafe_webhook_env(monkeypatch, tmp_path):
    gateway = load_gateway()
    events = []

    class FakeTelegramClient:
        def __init__(self, token, api_base="https://api.telegram.org", allow_delivery_state_mutation=False):
            events.append(("telegram_client", token, api_base, allow_delivery_state_mutation))

        def call(self, method, payload=None, timeout=35):
            events.append(("telegram_call", method, payload, timeout))
            raise AssertionError("startup must not call Telegram API methods")

        def get_updates(self, offset, timeout):
            events.append(("get_updates", offset, timeout))
            raise AssertionError("startup must not start polling before Gateway.run owns the receiver")

    class FakeFactoryClient:
        def __init__(self, control_url, control_urls):
            events.append(("factory_client", control_url, control_urls))

    class FakeGateway:
        def __init__(self, telegram, factory, owner_ids, state, poll_timeout):
            events.append(("gateway_init", owner_ids, poll_timeout))

        def run(self):
            events.append(("gateway_run",))

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("startup must not open network connections")

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_OWNER_IDS", "100")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_URL", "https://unsafe.example/hook")
    monkeypatch.setenv("TELEGRAM_DELETE_WEBHOOK", "1")
    monkeypatch.setenv("TELEGRAM_DROP_PENDING_UPDATES", "1")
    monkeypatch.setattr(sys, "argv", ["telegram_gateway.py", "--state-file", str(tmp_path / "state.json"), "--poll-timeout", "1"])
    monkeypatch.setattr(gateway.urllib.request, "urlopen", fail_urlopen)
    monkeypatch.setattr(gateway, "TelegramClient", FakeTelegramClient)
    monkeypatch.setattr(gateway, "FactoryClient", FakeFactoryClient)
    monkeypatch.setattr(gateway, "Gateway", FakeGateway)

    try:
        gateway.main()
    except SystemExit as exc:
        assert "refused to start polling" in str(exc)
    else:
        raise AssertionError("unsafe webhook environment did not refuse ordinary polling startup")
    assert ("telegram_client", "fake-token", "https://api.telegram.org", False) in events
    assert ("gateway_run",) not in events
    assert not any(event[0] in {"telegram_call", "get_updates"} for event in events)


def test_default_gateway_startup_without_webhook_env_starts_existing_polling_receiver(monkeypatch, tmp_path):
    gateway = load_gateway()
    events = []

    class FakeTelegramClient:
        def __init__(self, token, api_base="https://api.telegram.org", allow_delivery_state_mutation=False):
            events.append(("telegram_client", token, api_base, allow_delivery_state_mutation))

        def call(self, method, payload=None, timeout=35):
            events.append(("telegram_call", method, payload, timeout))
            raise AssertionError("startup must not call Telegram API methods")

        def get_updates(self, offset, timeout):
            events.append(("get_updates", offset, timeout))
            raise AssertionError("startup must not poll until Gateway.run owns the receiver")

    class FakeFactoryClient:
        def __init__(self, control_url, control_urls):
            events.append(("factory_client", control_url, control_urls))

    class FakeGateway:
        def __init__(self, telegram, factory, owner_ids, state, poll_timeout):
            events.append(("gateway_init", owner_ids, poll_timeout))

        def run(self):
            events.append(("gateway_run",))

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("startup must not open network connections")

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_OWNER_IDS", "100")
    monkeypatch.delenv("TELEGRAM_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOW_WEBHOOK_DELETE", raising=False)
    monkeypatch.delenv("TELEGRAM_DROP_PENDING_UPDATES", raising=False)
    monkeypatch.setattr(sys, "argv", ["telegram_gateway.py", "--state-file", str(tmp_path / "state.json"), "--poll-timeout", "1"])
    monkeypatch.setattr(gateway.urllib.request, "urlopen", fail_urlopen)
    monkeypatch.setattr(gateway, "TelegramClient", FakeTelegramClient)
    monkeypatch.setattr(gateway, "FactoryClient", FakeFactoryClient)
    monkeypatch.setattr(gateway, "Gateway", FakeGateway)

    assert gateway.main() == 0
    assert ("telegram_client", "fake-token", "https://api.telegram.org", False) in events
    assert ("gateway_run",) in events
    assert not any(event[0] in {"telegram_call", "get_updates"} for event in events)


def test_webhook_deletion_is_owner_approved_migration_only(monkeypatch):
    migration = load_webhook_migration()
    calls = []

    class FakeTelegramClient:
        def __init__(self, token, api_base="https://api.telegram.org", allow_delivery_state_mutation=False):
            calls.append(("client", token, api_base, allow_delivery_state_mutation))

        def call(self, method, payload=None, timeout=35):
            calls.append(("call", method, payload, timeout))
            return {"ok": True, "result": True}

    monkeypatch.setattr(migration, "TelegramClient", FakeTelegramClient)
    result = migration.delete_webhook_for_owner_approved_migration(
        "fake-token",
        migration.DELETE_WEBHOOK_APPROVAL,
        drop_pending_updates=False,
        api_base="https://telegram.invalid",
    )
    assert result == {"ok": True, "result": True}
    assert calls == [
        ("client", "fake-token", "https://telegram.invalid", True),
        ("call", "deleteWebhook", {"drop_pending_updates": "false"}, 35),
    ]

    try:
        migration.delete_webhook_for_owner_approved_migration("fake-token", "unsafe")
    except SystemExit as exc:
        assert "owner approval" in str(exc)
    else:
        raise AssertionError("webhook deletion did not require owner approval")


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


def test_gomesh_speed_gate_report_becomes_clean_russian_telegram_card():
    gateway = load_gateway()
    owner_sample = """
task_id: P0_TELEGRAM_GOMESH_REPORT_MESSAGE_FORMAT_2026_07_01
node: server-9fts
agent: agent-host-9fts
worktree: /var/lib/kolibri-agent/worktrees/P0_TELEGRAM/repo
stdout:
  raw speedtest output omitted
stderr:
  warning: retry noise
secret token: 123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef

Kolibri GoMesh speed/status report
Home endpoint: home.kolibri.local:9443
Health: healthy
Direct Mbps: 487.6
GoMesh Mbps: 214.8
Target: 300+ Mbps
Speed gate: FAILED
Selector status: safe-mode, GoMesh selector not promoted
pytest: 42 passed in 18.4s
Rollback backup paths: /etc/kolibri/gomesh-selector.conf.bak-20260701 /opt/kolibri/backups/gomesh-routes-20260701.json
Next action: tune exit selection and rerun the 300+ Mbps gate before enabling selector promotion.
"""
    task = {
        "state": "completed",
        "envelope": {"kind": "owner_remote_task"},
        "result": {"response": owner_sample},
    }

    message = gateway.format_task_status(task)

    assert message.startswith("Kolibri GoMesh: статус speed-gate")
    assert "Статус: не пройден" in message
    assert "Home endpoint: home.kolibri.local:9443" in message
    assert "Health: healthy" in message
    assert "direct 487.6 Mbps" in message
    assert "GoMesh 214.8 Mbps" in message
    assert "цель 300+ Mbps" in message
    assert "speed-gate провален" in message
    assert "Selector: safe-mode, GoMesh selector not promoted" in message
    assert "pytest 42 passed" in message
    assert "/etc/kolibri/gomesh-selector.conf.bak-20260701" in message
    assert "/opt/kolibri/backups/gomesh-routes-20260701.json" in message
    assert "Следующее действие: tune exit selection" in message
    for forbidden in [
        "task_id",
        "node:",
        "agent:",
        "stdout",
        "stderr",
        "/var/lib",
        "123456789:",
        "секрет",
        "Готово",
        "завершил",
    ]:
        assert forbidden.lower() not in message.lower()


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


def test_chat_envelope_selects_only_online_runner_capable_fallback_node():
    gateway = load_gateway()
    message = {
        "message_id": 455,
        "chat": {"id": 100, "type": "private"},
        "from": {"id": 100},
        "text": "что в работе?",
    }
    snapshot = {
        "nodes": [
            {"node_id": "offline", "health": "offline", "capabilities": ["generic_implementation", "runner:codex"]},
            {"node_id": "generic-only", "health": "online", "capabilities": ["generic_implementation"]},
            {"node_id": "blocked", "health": "online", "capabilities": ["generic_implementation", "runner:codex"], "runners": {"codex": {"status": "blocked"}}},
            {"node_id": "good", "health": "online", "capabilities": ["generic_implementation", "runner:codex"], "runners": {"codex": {"status": "available"}}},
        ]
    }

    envelope = gateway.build_chat_envelope(message, message["text"], snapshot)

    assert envelope["runner"] == "codex"
    assert envelope["target_node"] == "good"


def test_chat_envelope_omits_target_when_only_avoided_runner_node_matches():
    gateway = load_gateway()
    message = {
        "message_id": 456,
        "chat": {"id": 100, "type": "private"},
        "from": {"id": 100},
        "text": "что в работе?",
    }
    snapshot = {
        "nodes": [
            {"node_id": "good", "health": "online", "capabilities": ["generic_implementation", "runner:codex"], "runners": {"codex": {"status": "available"}}},
        ]
    }
    envelope = gateway.build_chat_envelope(message, message["text"], snapshot)
    envelope["avoid_nodes"] = ["good"]

    assert gateway.select_runner_node(snapshot, envelope["runner"], envelope["avoid_nodes"]) is None


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
            return {
                "nodes": [{
                    "node_id": "home-live",
                    "health": "online",
                    "capabilities": ["generic_implementation", "runner:codex"],
                    "runners": {"codex": {"status": "available"}},
                }]
            }

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
    assert factory.envelopes[0]["target_node"] == "home-live"
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


def test_submit_chat_task_control_plane_failure_is_redacted_human_message(tmp_path):
    gateway = load_gateway()

    class Telegram:
        def __init__(self):
            self.messages = []

        def send_message(self, chat_id, text):
            self.messages.append((chat_id, text))

    class Factory:
        def create_task(self, envelope):
            raise RuntimeError(
                "POST /v1/tasks failed for task_id=TGCHAT-20260702120000 node=primary "
                "path=/var/lib/kolibri-agent/private token=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
            )

        def nodes(self):
            return {"nodes": []}

        def get_tasks(self):
            return {"tasks": [], "queue": []}

    telegram = Telegram()
    state = gateway.StateStore(tmp_path / "state.json")
    app = gateway.Gateway(telegram, Factory(), {100}, state, 1)
    message = {"message_id": 60, "chat": {"id": 100, "type": "private"}, "from": {"id": 100}, "text": "как дела?"}

    app.submit_chat_task(message, message["text"])

    assert len(telegram.messages) == 1
    reply = telegram.messages[0][1]
    assert "Control Plane" in reply
    assert "чат-задачу" in reply
    for forbidden in ["task_id", "TGCHAT", "node=", "/var/lib", "123456789:", "token"]:
        assert forbidden not in reply


def test_owner_commands_return_summaries_without_internal_ids(tmp_path):
    gateway = load_gateway()

    class Telegram:
        def __init__(self):
            self.messages = []

        def send_message(self, chat_id, text):
            self.messages.append((chat_id, text))

    class Factory:
        def nodes(self):
            return {
                "nodes": [
                    {
                        "node_id": "primary-candidate",
                        "agent_id": "agent-host-primary",
                        "pid": 4242,
                        "health": "online",
                        "current_task": "TG-20260702120100-secret",
                        "runners": {"codex": {"status": "available"}},
                    },
                    {
                        "node_id": "node-private",
                        "agent_id": "agent-host-private",
                        "pid": 5252,
                        "health": "offline",
                        "draining": True,
                    },
                ]
            }

        def get_tasks(self):
            return {
                "queue": ["TG-20260702120200-private-owner-task"],
                "tasks": [
                    {"task_id": "TG-20260702120200-private-owner-task", "state": "queued"},
                    {"task_id": "TGCHAT-20260702120300-private-chat", "state": "running"},
                    {"task_id": "TG-20260702120400-private-failed", "state": "failed"},
                    {"task_id": "TG-20260702120500-private-done", "state": "completed"},
                ],
            }

    telegram = Telegram()
    state = gateway.StateStore(tmp_path / "state.json")
    app = gateway.Gateway(telegram, Factory(), {100}, state, 1)
    base = {"message_id": 61, "chat": {"id": 100, "type": "private"}, "from": {"id": 100}}

    app.handle_command({**base, "text": "/nodes"}, "/nodes")
    app.handle_command({**base, "text": "/agents"}, "/agents")
    app.handle_command({**base, "text": "/queue"}, "/queue")

    assert len(telegram.messages) == 3
    combined = "\n".join(text for _, text in telegram.messages)
    assert "Команда: онлайн 1 из 2." in combined
    assert "Агент-хосты на связи: 1 из 2." in combined
    assert "Очередь: 1." in combined
    assert "Требуют разбора: 1." in combined
    for forbidden in [
        "primary-candidate",
        "node-private",
        "agent-host",
        "pid",
        "TG-202607",
        "TGCHAT",
        "private-owner",
        "/var/lib",
        "task_id",
    ]:
        assert forbidden not in combined
