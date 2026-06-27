import argparse
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_GREETING_TEMPLATE = "Привет. Я на связи. Могу рассказать о фабрике или принять задачу в работу."


def load_agent_host():
    spec = importlib.util.spec_from_file_location("agent_host", ROOT / "ops" / "agent_host.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_telegram_chat_prompt_does_not_include_fixed_greeting_template(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.setattr(agent_host.shutil, "which", lambda name: "/usr/bin/mimo" if name == "mimo" else None)

    class Host(agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []
            self.commands = []
            self.last_logs = None

        def post(self, path, body):
            self.posts.append((path, body))
            return body

        def run_command(self, command, cwd, stdout_path, stderr_path, task, branch, logs, env=None):
            del cwd, task, branch, logs, env
            self.commands.append(command)
            event = {"part": {"type": "text", "text": "Здравствуйте. Вижу контекст и отвечаю по делу."}}
            stdout_path.write_text(
                f"$ {' '.join(command)}\n"
                + json.dumps(event, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            stderr_path.write_text("", encoding="utf-8")
            self.last_logs = (stdout_path, stderr_path)

    args = argparse.Namespace(
        control_url="http://127.0.0.1:9101",
        node_id="primary-candidate",
        agent_id="agent-host-primary",
        capabilities="generic_implementation",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )
    host = Host(args)
    task = {
        "task_id": "TGCHAT-1",
        "attempt": 1,
        "attempt_id": "TGCHAT-1-attempt-1",
        "envelope": {
            "kind": "telegram_chat_response",
            "message": "Привет",
            "factory_snapshot": {
                "memory": {
                    "recent_messages": [{"role": "owner", "text": "Привет"}],
                    "last_work_request": {"text": "Сделай живой Telegram-диалог", "state": "running"},
                }
            },
        },
    }

    result = host.run_telegram_chat_response(task)

    assert result["kind"] == "telegram_chat_response"
    assert result["response"] == "Здравствуйте. Вижу контекст и отвечаю по делу."
    prompt = host.commands[0][-1]
    assert "каждый ответ должен быть заново сгенерирован" in prompt
    assert FORBIDDEN_GREETING_TEMPLATE not in prompt
    assert host.last_logs is not None
    stdout_path, stderr_path = host.last_logs
    assert FORBIDDEN_GREETING_TEMPLATE not in stdout_path.read_text(encoding="utf-8")
    assert FORBIDDEN_GREETING_TEMPLATE not in stderr_path.read_text(encoding="utf-8")
