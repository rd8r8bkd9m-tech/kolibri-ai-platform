import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_dispatcher_exposes_required_commands():
    dispatch = (ROOT / "ops" / "kolibri-dispatch").read_text(encoding="utf-8")
    for command in ["doctor", "nodes", "submit", "status", "collect", "cancel", "drain"]:
        assert f'"{command}"' in dispatch


def test_control_plane_states_are_declared():
    control = load_module(ROOT / "ops" / "factory_control.py")
    assert {
        control.STATE_QUEUED,
        control.STATE_LEASED,
        control.STATE_RUNNING,
        control.STATE_WAITING_REVIEW,
        control.STATE_REVIEW,
        control.STATE_COMPLETED,
        control.STATE_FAILED,
        control.STATE_CANCELLED,
        control.STATE_RETRY,
        control.STATE_DEAD,
    } == {
        "queued",
        "leased",
        "running",
        "waiting_review",
        "review",
        "completed",
        "failed",
        "cancelled",
        "retry_scheduled",
        "dead_letter",
    }


def test_agent_host_supports_required_task_kinds():
    agent = (ROOT / "ops" / "agent_host.py").read_text(encoding="utf-8")
    assert "impl_factory_smoke" in agent
    assert "impl_retry_error_clearance" in agent
    assert "owner_remote_task" in agent
    assert "telegram_chat_response" in agent
    assert "orchestrator_chat_response" in agent
    assert "review_pr" in agent
    assert "read_only_probe" in agent
    assert "root_goal" in agent
    assert "runtime_exec_hardening_probe" in agent
    memory = (ROOT / "ops" / "orchestrator_memory.py").read_text(encoding="utf-8")
    assert "last_work_request" in memory
    assert "open_expectations" in memory


def test_agent_host_publishes_filesystem_manifest():
    agent = (ROOT / "ops" / "agent_host.py").read_text(encoding="utf-8")
    assert "filesystem_manifest" in agent
    assert "namespace_prefix" in agent
    assert "/kolibri/nodes/" in agent
    assert "worktrees" in agent
    assert "artifacts" in agent
    assert "KOLIBRI_FILE_ROOTS" in agent


def test_control_plane_exposes_unified_filesystem_namespace():
    control = (ROOT / "ops" / "factory_control.py").read_text(encoding="utf-8")
    assert "build_filesystem_namespace" in control
    assert 'path == "/v1/filesystem"' in control
    assert '"transport": "mesh-api/control-plane"' in control
    assert '"namespace": "/kolibri"' in control
    assert "write_policy" in control


def test_orchestrator_roster_has_human_role_cards():
    roster = load_module(ROOT / "ops" / "orchestrator_roster.py")
    assert roster.ORCHESTRATOR_CARD["name"] == "Директор"
    engineer = roster.node_card({"node_id": "9fts", "health": "online", "capabilities": ["implementation"]})
    reviewer = roster.node_card({"node_id": "new", "health": "online", "capabilities": ["review"]})
    assert engineer["name"] == "Инженер"
    assert reviewer["name"] == "Ревьюер"
    assert engineer["health"] == "online"


def test_agent_host_extracts_agent_message_jsonl():
    agent = load_module(ROOT / "ops" / "agent_host.py")
    assert agent.text_from_json_event({
        "type": "item.completed",
        "item": {"type": "agent_message", "text": "живой ответ"},
    }) == "живой ответ"


def test_agent_host_disables_codex_cli_runner(monkeypatch, tmp_path):
    agent = load_module(ROOT / "ops" / "agent_host.py")
    host = agent.AgentHost(SimpleNamespace(
        control_urls="http://127.0.0.1:9101",
        control_url="http://127.0.0.1:9101",
        node_id="primary-candidate",
        agent_id="agent-host-primary",
        capabilities="generic_implementation",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        poll_interval=1,
        heartbeat_interval=1,
        lease_refresh=1,
        max_inflight=1,
    ))
    try:
        host.build_text_runner_command("codex", "ответь живо", tmp_path, "telegram-chat-test")
    except RuntimeError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("codex CLI runner must stay disabled in server runtime")


def test_agent_host_publishes_safe_filesystem_manifest(monkeypatch, tmp_path):
    agent = load_module(ROOT / "ops" / "agent_host.py")
    runtime_repo = tmp_path / "runtime-repo"
    owner_project = tmp_path / "owner-project"
    cache_root = tmp_path / "cache"
    mirror_root = tmp_path / "mirror"
    for path in (runtime_repo, owner_project, cache_root, mirror_root):
        path.mkdir()
    monkeypatch.setenv("KOLIBRI_RUNTIME_REPO", str(runtime_repo))
    monkeypatch.setenv("KOLIBRI_OWNER_PROJECT_PATH", str(owner_project))
    monkeypatch.setenv("KOLIBRI_FILE_ROOTS", f"cache={cache_root}:rw,mirror={mirror_root}:ro")
    host = agent.AgentHost(SimpleNamespace(
        control_urls="http://127.0.0.1:9101",
        control_url="http://127.0.0.1:9101",
        node_id="node-a",
        agent_id="agent-host-node-a",
        capabilities="generic_implementation",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "worktrees"),
        artifact_root=str(tmp_path / "artifacts"),
        poll_interval=1,
        heartbeat_interval=1,
        lease_refresh=1,
        max_inflight=1,
    ))

    posted = []
    monkeypatch.setattr(host, "post", lambda path, body: posted.append((path, body)))
    manifest = host.filesystem_manifest()
    host.register()
    host.node_heartbeat(active_task="TASK-1")

    assert manifest["namespace_prefix"] == "/kolibri/nodes/node-a"
    assert manifest["mode"] == "mesh_api_namespace"
    assert "no shared writable root disk" in manifest["write_policy"]
    roots = {root["name"]: root for root in manifest["roots"]}
    assert {"worktrees", "artifacts", "runtime-repo", "owner-project", "cache", "mirror"} <= set(roots)
    assert roots["worktrees"]["namespace"] == "/kolibri/nodes/node-a/worktrees"
    assert roots["cache"]["writable"] is True
    assert roots["mirror"]["writable"] is False
    assert posted[0][1]["filesystem"]["namespace_prefix"] == "/kolibri/nodes/node-a"
    assert posted[1][1]["filesystem"]["roots"]


class FakeRedis:
    def __init__(self, values):
        self.values = values

    def command(self, *parts):
        command = parts[0]
        if command == "SMEMBERS":
            return ["node-a", "node-b"]
        if command == "GET":
            return self.values.get(parts[1])
        raise AssertionError(f"unexpected redis command: {parts!r}")


def test_control_plane_builds_unified_filesystem_namespace(monkeypatch):
    control = load_module(ROOT / "ops" / "factory_control.py")
    node_a = {
        "node_id": "node-a",
        "hostname": "host-a",
        "agent_id": "agent-a",
        "health": "online",
        "filesystem": {
            "namespace_prefix": "/unsafe/ignored",
            "mode": "unsafe",
            "write_policy": "unsafe",
            "roots": [
                {
                    "name": "worktrees",
                    "path": "/srv/worktrees",
                    "purpose": "per-task writable worktrees",
                    "exists": True,
                    "writable": True,
                    "secret_token": "must-not-leak",
                },
            ],
        },
    }
    node_b = {
        "node_id": "node-b",
        "hostname": "host-b",
        "agent_id": "agent-b",
        "health": "online",
        "filesystem": {
            "roots": [
                {
                    "name": "artifacts",
                    "path": "/srv/artifacts",
                    "purpose": "task logs and structured results",
                    "exists": True,
                    "writable": True,
                },
            ],
        },
    }
    monkeypatch.setattr(control, "redis", FakeRedis({
        control.node_key("node-a"): json.dumps(node_a),
        control.node_key("node-b"): json.dumps(node_b),
    }))

    namespace = control.build_filesystem_namespace()

    assert namespace["namespace"] == "/kolibri"
    assert namespace["transport"] == "mesh-api/control-plane"
    assert namespace["mode"] == "mesh_api_namespace"
    assert "no shared writable root disk" in namespace["write_policy"]
    assert namespace["root_count"] == 2
    assert namespace["nodes"][0]["namespace_prefix"] == "/kolibri/nodes/node-a"
    assert namespace["roots"][0]["namespace"] == "/kolibri/nodes/node-a/worktrees"
    assert namespace["roots"][0]["writable"] is True
    assert "secret_token" not in namespace["roots"][0]


def test_macbook_filesystem_publisher_exports_read_only_namespace(tmp_path):
    publisher = load_module(ROOT / "ops" / "macbook_filesystem_publisher.py")
    manifest = publisher.build_filesystem_manifest("macbook", tmp_path)
    roots = {root["name"]: root for root in manifest["roots"]}

    assert manifest["namespace_prefix"] == "/kolibri/nodes/macbook"
    assert manifest["mode"] == "mesh_api_namespace"
    assert "read-only MacBook namespace" in manifest["write_policy"]
    assert roots["root"]["path"] == "/"
    assert roots["root"]["namespace"] == "/kolibri/nodes/macbook/root"
    assert roots["home"]["writable"] is False
    assert roots["project"]["path"] == str(tmp_path)
    assert all(root["writable"] is False for root in manifest["roots"])


def test_mesh_control_ingress_only_allows_narrow_control_plane_paths():
    ingress = load_module(ROOT / "ops" / "mesh_control_ingress.py")

    assert ingress.path_allowed("POST", "/v1/nodes/register")
    assert ingress.path_allowed("POST", "/v1/nodes/agent-01/heartbeat")
    assert ingress.path_allowed("POST", "/v1/tasks/lease")
    assert ingress.path_allowed("POST", "/v1/tasks/TASK-1/heartbeat")
    assert ingress.path_allowed("GET", "/v1/filesystem")
    assert not ingress.path_allowed("POST", "/api/exec")
    assert not ingress.path_allowed("POST", "/task/execute")
    assert not ingress.path_allowed("GET", "/etc/passwd")
