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


def make_args(tmp_path):
    return argparse.Namespace(
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


def make_chat_task(task_id, message):
    return {
        "task_id": task_id,
        "kind": "telegram_chat_response",
        "attempt": 1,
        "attempt_id": f"{task_id}-attempt-1",
        "lease_id": f"{task_id.lower()}-lease-1",
        "fencing_token": 1,
        "executor_release_id": "unversioned",
        "envelope": {
            "kind": "telegram_chat_response",
            "message": message,
            "factory_snapshot": {
                "memory": {
                    "recent_messages": [{"role": "owner", "text": message}],
                    "last_work_request": {"text": "Сделай живой Telegram-диалог", "state": "running"},
                }
            },
        },
    }


def test_telegram_chat_prompt_does_not_include_fixed_greeting_template(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.setenv("KOLIBRI_TELEGRAM_RUNNER", "mimo")
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

        def run_command(self, command, cwd, stdout_path, stderr_path, task, branch, logs, env=None, command_label=None):
            del cwd, task, branch, logs, env
            self.commands.append((command, command_label))
            event = {"part": {"type": "text", "text": "Здравствуйте. Вижу контекст и отвечаю по делу."}}
            stdout_path.write_text(
                f"$ {command_label}\n"
                + json.dumps(event, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            stderr_path.write_text("", encoding="utf-8")
            self.last_logs = (stdout_path, stderr_path)

    host = Host(make_args(tmp_path))
    task = make_chat_task("TGCHAT-1", "Привет")

    result = host.run_telegram_chat_response(task)

    assert result["kind"] == "telegram_chat_response"
    assert result["response"] == "Здравствуйте. Вижу контекст и отвечаю по делу."
    prompt = host.commands[0][0][-1]
    assert "каждый ответ должен быть заново сгенерирован" in prompt
    assert FORBIDDEN_GREETING_TEMPLATE not in prompt
    assert host.last_logs is not None
    stdout_path, stderr_path = host.last_logs
    assert FORBIDDEN_GREETING_TEMPLATE not in stdout_path.read_text(encoding="utf-8")
    assert FORBIDDEN_GREETING_TEMPLATE not in stderr_path.read_text(encoding="utf-8")


def test_telegram_chat_uses_codex_when_ai_runner_is_codex(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.delenv("KOLIBRI_TELEGRAM_RUNNER", raising=False)
    monkeypatch.setenv("KOLIBRI_AI_RUNNER", "codex")
    monkeypatch.setattr(agent_host.shutil, "which", lambda name: f"/usr/bin/{name}" if name in {"codex", "mimo"} else None)

    class Host(agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []
            self.commands = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

        def run_command(self, command, cwd, stdout_path, stderr_path, task, branch, logs, env=None, command_label=None):
            del cwd, task, branch, logs, env
            self.commands.append((command, command_label))
            event = {"msg": {"type": "agent_message", "message": "Принял задачу."}}
            stdout_path.write_text(json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")

    host = Host(make_args(tmp_path))
    result = host.run_telegram_chat_response(make_chat_task("TGCHAT-CODEX", "Проверь статус"))

    assert result["response"] == "Принял задачу."
    command, command_label = host.commands[0]
    assert command[:5] == ["/usr/bin/codex", "exec", "--json", "--skip-git-repo-check", "--sandbox"]
    assert "danger-full-access" in command
    assert command[-1].endswith("Сообщение владельца: Проверь статус")
    assert "/usr/bin/mimo" not in command
    assert command_label == "/usr/bin/codex exec --json --skip-git-repo-check --sandbox danger-full-access <prompt>"


def test_telegram_chat_runner_error_does_not_expose_owner_prompt_in_failure_payload(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.delenv("KOLIBRI_TELEGRAM_RUNNER", raising=False)
    monkeypatch.setenv("KOLIBRI_AI_RUNNER", "codex")
    monkeypatch.setattr(agent_host.shutil, "which", lambda name: "/usr/bin/codex" if name == "codex" else None)
    owner_message = "не показывай это сообщение владельца в технической ошибке"

    class Host(agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

        def run_command(self, command, cwd, stdout_path, stderr_path, task, branch, logs, env=None, command_label=None):
            del command, cwd, task, branch, logs, env
            stdout_path.write_text(f"$ {command_label}\n", encoding="utf-8")
            stderr_path.write_text("Network request failed\n", encoding="utf-8")
            raise RuntimeError(f"command failed with rc=6: {command_label}")

    host = Host(make_args(tmp_path))
    host.run_task(make_chat_task("TGCHAT-ERR", owner_message))

    fail_posts = [(path, body) for path, body in host.posts if path.endswith("/fail")]
    assert len(fail_posts) == 1
    _, fail_body = fail_posts[0]
    service_payload = json.dumps(fail_body, ensure_ascii=False)
    assert owner_message not in service_payload
    assert "Сообщение владельца" not in service_payload
    assert "<prompt>" in service_payload
    result_path = Path(fail_body["result_reference"])
    assert owner_message not in result_path.read_text(encoding="utf-8")
    stdout_path = tmp_path / "artifacts" / "TGCHAT-ERR" / "TGCHAT-ERR-attempt-1" / "stdout.log"
    assert owner_message not in stdout_path.read_text(encoding="utf-8")

def test_parse_codex_agent_message_jsonl(tmp_path):
    agent_host = load_agent_host()
    stdout = tmp_path / "stdout.log"
    stdout.write_text(
        '$ codex exec --json <prompt>\n'
        + json.dumps({"type": "thread.started", "thread_id": "t1"}, ensure_ascii=False)
        + "\n"
        + json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "Живой ответ директора."}}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    assert agent_host.AgentHost.parse_json_text_response(stdout) == "Живой ответ директора."


def test_api_runner_missing_auth_is_reported_without_prompt(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.setenv("KOLIBRI_TELEGRAM_RUNNER", "api")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("KOLIBRI_API_RUNNER_TOKEN", raising=False)

    class Host(agent_host.AgentHost):
        def post(self, path, body):
            return body

    host = Host(make_args(tmp_path))
    try:
        host.run_telegram_chat_response(make_chat_task("TGCHAT-API", "секретный текст владельца"))
    except RuntimeError as exc:
        message = str(exc)
        assert "api runner auth is not configured" in message
        assert "секретный текст владельца" not in message
    else:
        raise AssertionError("expected RuntimeError")


def test_local_llm_runner_missing_url_is_reported_without_prompt(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    monkeypatch.setenv("KOLIBRI_TELEGRAM_RUNNER", "local_llm")
    monkeypatch.delenv("KOLIBRI_LOCAL_LLM_URL", raising=False)

    class Host(agent_host.AgentHost):
        def post(self, path, body):
            return body

    host = Host(make_args(tmp_path))
    try:
        host.run_telegram_chat_response(make_chat_task("TGCHAT-LOCAL", "приватный вопрос"))
    except RuntimeError as exc:
        message = str(exc)
        assert "local_llm runner is not configured" in message
        assert "приватный вопрос" not in message
    else:
        raise AssertionError("expected RuntimeError")
