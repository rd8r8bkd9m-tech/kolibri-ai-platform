import argparse
import base64
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="


def load_agent_host():
    spec = importlib.util.spec_from_file_location("agent_host", ROOT / "ops" / "agent_host.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_agent_host_generates_telegram_image_with_configured_command(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    command = (
        "python3 -c \"import base64, os, pathlib; "
        "pathlib.Path(os.environ['KOLIBRI_IMAGE_OUTPUT_PATH']).write_bytes("
        f"base64.b64decode('{TINY_PNG_B64}'))\""
    )
    monkeypatch.setenv("KOLIBRI_IMAGE_GENERATOR_CMD", command)

    class Host(agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

    args = argparse.Namespace(
        control_url="http://127.0.0.1:9101",
        node_id="primary-candidate",
        agent_id="agent-host-primary",
        capabilities="image_generation",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )
    host = Host(args)
    task = {
        "task_id": "TGIMG-1",
        "attempt": 1,
        "attempt_id": "TGIMG-1-attempt-1",
        "envelope": {
            "kind": "telegram_image_generation",
            "prompt": "Нарисуй птичку Колибри",
            "caption": "Готово.",
        },
    }

    result = host.run_telegram_image_generation(task)

    image_path = Path(result["image_path"])
    assert image_path.exists()
    assert image_path.read_bytes() == base64.b64decode(TINY_PNG_B64)
    assert result["kind"] == "telegram_image_generation"
    assert result["image_mime_type"] == "image/png"
    assert result["caption"] == "Готово."
    assert result["image_b64"] == TINY_PNG_B64
    assert "OPENAI_API_KEY" not in result
    assert any(path.endswith("/heartbeat") for path, _ in host.posts)


def test_agent_host_control_plane_failover(tmp_path, monkeypatch):
    agent_host = load_agent_host()
    calls = []

    def fake_request(method, url, body=None, timeout=20):
        calls.append((method, url, body, timeout))
        if url.startswith("http://down"):
            raise RuntimeError("down")
        return {"ok": True}

    monkeypatch.setattr(agent_host, "request", fake_request)
    args = argparse.Namespace(
        control_url="http://down:9101",
        control_urls="http://down:9101,http://alive:9101",
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
    host = agent_host.AgentHost(args)
    assert host.get("/health") == {"ok": True}
    assert calls[0][1] == "http://down:9101/health"
    assert calls[1][1] == "http://alive:9101/health"
    assert host.control_url == "http://alive:9101"
    host.post("/v1/tasks/lease", {"node_id": "primary-candidate"})
    assert calls[-1][1] == "http://alive:9101/v1/tasks/lease"
