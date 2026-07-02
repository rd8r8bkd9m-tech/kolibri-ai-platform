import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_control():
    spec = importlib.util.spec_from_file_location("factory_control", ROOT / "ops" / "factory_control.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_miniapp_task_envelope_is_owner_scoped_and_runner_aware():
    control = load_control()
    auth = {"ok": True, "role": "owner", "user": {"id": 100}}
    body = {"objective": "Проверь CI и артефакты", "runner": "api", "task_id": "TGAPP-1"}
    envelope = control.miniapp_task_envelope(body, auth)
    assert envelope["kind"] == "owner_remote_task"
    assert envelope["source"] == {
        "kind": "telegram_miniapp",
        "user_id": 100,
        "role": "owner",
        "accepted_at": envelope["source"]["accepted_at"],
    }
    assert envelope["runner"] == "api"
    assert envelope["runner_policy"]["diagnostics"]
    assert "TELEGRAM_BOT_TOKEN" not in str(envelope)


def test_miniapp_task_envelope_requires_objective():
    control = load_control()
    try:
        control.miniapp_task_envelope({}, {"role": "owner", "user": {"id": 100}})
    except ValueError as exc:
        assert "objective is required" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_miniapp_console_cards_are_sanitized_and_artifact_aware():
    control = load_control()
    task = {
        "task_id": "TGAPP-UI-1",
        "state": "completed",
        "attempt": 1,
        "lease_owner": "9fts:agent-host-9fts",
        "created_at": "2026-07-02T00:00:00+00:00",
        "updated_at": "2026-07-02T00:01:00+00:00",
        "envelope": {
            "kind": "owner_remote_task",
            "objective": "Собери фабричный пульт и верни PR",
            "runner": "codex",
        },
        "result": {
            "pull_request_url": "https://github.example/pr/1",
            "artifact_paths": ["docs/agent/runs/result.json"],
        },
    }
    node = {
        "node_id": "9fts",
        "display_name": "Инженер",
        "health": "online",
        "capabilities": ["generic_implementation", "runner:codex"],
        "runners": {"codex": {"status": "available"}},
        "agent_id": "agent-host-9fts",
    }

    task_card = control.task_console_card(task)
    node_card = control.node_console_card(node)

    assert task_card["task_id"] == "TGAPP-UI-1"
    assert task_card["node_id"] == "9fts"
    assert task_card["objective"] == "Собери фабричный пульт и верни PR"
    assert task_card["artifacts"]["count"] == 2
    assert task_card["artifacts"]["items"][0]["kind"] == "pull_request_url"
    assert node_card["name"] == "Инженер"
    assert node_card["capabilities"] == ["generic_implementation", "runner:codex"]


def test_telegram_miniapp_factory_console_surfaces_required_views():
    html = (ROOT / "frontend" / "public" / "telegram-miniapp.html").read_text(encoding="utf-8")

    assert "Пульт фабрики Kolibri" in html
    assert "Список задач" in html
    assert "Агенты" in html
    assert "Здоровье серверов" in html
    assert "Артефакты" in html
    assert "/v1/superfactory/status" in html
    assert "/v1/superfactory/tasks" in html
    assert "X-Telegram-Init-Data" in html
    assert 'class="tabs"' in html
