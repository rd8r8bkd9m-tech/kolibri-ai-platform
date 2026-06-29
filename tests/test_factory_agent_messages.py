import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_control():
    spec = importlib.util.spec_from_file_location("factory_control", ROOT / "ops" / "factory_control.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_agent_message_normalization_defaults_to_all_feed():
    control = load_control()

    message = control.normalize_agent_message({"sender": "node-a", "body": "done"})

    assert message["sender"] == "node-a"
    assert message["recipients"] == ["all"]
    assert message["kind"] == "status"
    assert message["body"] == "done"
    assert message["message_id"].startswith("MSG-")


def test_agent_message_normalization_supports_addressed_artifact_updates():
    control = load_control()

    message = control.normalize_agent_message(
        {
            "from": "node-a",
            "to": "node-b,reviewer",
            "kind": "task_completed",
            "topic": "generic_implementation",
            "task_id": "TASK-1",
            "message": "completed",
            "artifacts": [{"result_path": "/tmp/result.json"}],
        }
    )

    assert message["sender"] == "node-a"
    assert message["recipients"] == ["node-b", "reviewer"]
    assert message["kind"] == "task_completed"
    assert message["task_id"] == "TASK-1"
    assert message["artifacts"][0]["result_path"] == "/tmp/result.json"
