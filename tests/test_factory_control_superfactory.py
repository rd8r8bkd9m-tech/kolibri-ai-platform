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
