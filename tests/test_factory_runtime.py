import importlib.util
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch


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


def test_control_plane_classifies_stale_online_heartbeat_as_stale():
    control = load_module(ROOT / "ops" / "factory_control.py")
    now = datetime.now(timezone.utc)
    node = control.classify_node_freshness(
        {
            "node_id": "worker-1",
            "health": "online",
            "heartbeat_at": (now - timedelta(seconds=600)).isoformat(),
        },
        now.timestamp(),
    )

    assert node["reported_health"] == "online"
    assert node["freshness"] == "stale"
    assert node["health"] == "stale"
    assert node["heartbeat_age_seconds"] == 600
    assert control.node_health_counts([node]) == {"fresh": 0, "degraded": 0, "stale": 1, "online": 0, "total": 1}


def test_control_plane_counts_fresh_degraded_and_stale_nodes():
    control = load_module(ROOT / "ops" / "factory_control.py")
    now = datetime.now(timezone.utc)
    nodes = [
        control.classify_node_freshness({"node_id": "fresh", "health": "online", "heartbeat_at": (now - timedelta(seconds=5)).isoformat()}, now.timestamp()),
        control.classify_node_freshness({"node_id": "degraded", "health": "online", "heartbeat_at": (now - timedelta(seconds=45)).isoformat()}, now.timestamp()),
        control.classify_node_freshness({"node_id": "stale", "health": "online", "heartbeat_at": (now - timedelta(seconds=120)).isoformat()}, now.timestamp()),
    ]

    assert [node["freshness"] for node in nodes] == ["fresh", "degraded", "stale"]
    assert control.node_health_counts(nodes) == {"fresh": 1, "degraded": 1, "stale": 1, "online": 1, "total": 3}


def test_agent_host_supports_required_task_kinds():
    agent = (ROOT / "ops" / "agent_host.py").read_text(encoding="utf-8")
    assert "impl_factory_smoke" in agent
    assert "impl_retry_error_clearance" in agent
    assert "telegram_chat_response" in agent
    assert "orchestrator_chat_response" in agent
    assert "telegram_image_generation" in agent
    assert "review_pr" in agent
    assert "read_only_probe" in agent
    memory = (ROOT / "ops" / "orchestrator_memory.py").read_text(encoding="utf-8")
    assert "last_work_request" in memory
    assert "open_expectations" in memory


def test_agent_host_filesystem_manifest_exposes_project_roots(tmp_path, monkeypatch):
    agent = load_module(ROOT / "ops" / "agent_host.py")
    work_root = tmp_path / "worktrees"
    artifact_root = tmp_path / "artifacts"
    runtime_repo = tmp_path / "runtime-repo"
    owner_project = tmp_path / "owner-project"
    extra_root = tmp_path / "readonly-root"
    runtime_repo.mkdir()
    owner_project.mkdir()
    extra_root.mkdir()
    monkeypatch.setenv("KOLIBRI_RUNTIME_REPO", str(runtime_repo))
    monkeypatch.setenv("KOLIBRI_OWNER_PROJECT_PATH", str(owner_project))
    monkeypatch.setenv("KOLIBRI_FILE_ROOTS", f"root={extra_root}:ro")

    host = agent.AgentHost(SimpleNamespace(
        control_url="http://control.local:9101",
        control_urls="http://control.local:9101",
        node_id="server kfrm",
        agent_id="agent-test",
        capabilities="read_only_probe",
        repo_url="git@example.com:repo.git",
        work_root=str(work_root),
        artifact_root=str(artifact_root),
        heartbeat_interval=10,
        lease_refresh=5,
        max_inflight=1,
    ))

    manifest = host.filesystem_manifest()
    roots = {root["name"]: root for root in manifest["roots"]}

    assert manifest["namespace_prefix"] == "/kolibri/nodes/server-kfrm"
    assert manifest["mode"] == "mesh_api_namespace"
    assert roots["worktrees"]["namespace"] == "/kolibri/nodes/server-kfrm/worktrees"
    assert roots["artifacts"]["exists"] is True
    assert roots["runtime-repo"]["path"] == str(runtime_repo)
    assert roots["owner-project"]["path"] == str(owner_project)
    assert roots["root"]["writable"] is False


def test_agent_host_loop_skips_malformed_lease_response_without_crashing():
    agent = load_module(ROOT / "ops" / "agent_host.py")
    host = object.__new__(agent.AgentHost)
    host.heartbeat_interval = 0
    heartbeats = []
    leases = [{"status": "blocked", "reason": "target_node_unavailable"}]
    runs = []

    def register():
        return None

    def node_heartbeat(active_task=None):
        heartbeats.append(active_task)

    def lease():
        if leases:
            return leases.pop(0)
        agent.STOP = True
        return None

    host.register = register
    host.node_heartbeat = node_heartbeat
    host.lease = lease
    host.run_task = runs.append

    agent.STOP = False
    try:
        with patch.object(agent.time, "sleep", lambda _seconds: None):
            host.loop()
    finally:
        agent.STOP = False

    assert runs == []
    assert all(active_task is None for active_task in heartbeats)



def test_orchestrator_roster_has_human_role_cards():
    roster = load_module(ROOT / "ops" / "orchestrator_roster.py")
    assert roster.ORCHESTRATOR_CARD["name"] == "Директор"
    engineer = roster.node_card({"node_id": "9fts", "health": "online", "capabilities": ["implementation"]})
    reviewer = roster.node_card({"node_id": "new", "health": "online", "capabilities": ["review"]})
    assert engineer["name"] == "Инженер"
    assert reviewer["name"] == "Ревьюер"
    assert engineer["health"] == "online"


def test_control_plane_runner_compatibility_filters_blocked_and_avoided_nodes():
    control = load_module(ROOT / "ops" / "factory_control.py")
    task = control.normalize_task({
        "kind": "owner_remote_task",
        "runner": "mimo",
        "required_capability": "generic_implementation",
        "avoid_nodes": ["avoid-me"],
    })

    assert control.compatible(
        task,
        "healthy",
        ["generic_implementation", "runner:mimo"],
        {"runners": {"mimo": {"status": "available"}}},
    ) is True
    assert control.compatible(
        task,
        "missing-runner-cap",
        ["generic_implementation"],
        {"runners": {"mimo": {"status": "available"}}},
    ) is False
    assert control.compatible(
        task,
        "blocked",
        ["generic_implementation", "runner:mimo"],
        {"runners": {"mimo": {"status": "blocked"}}},
    ) is False
    assert control.compatible(
        task,
        "avoid-me",
        ["generic_implementation", "runner:mimo"],
        {"runners": {"mimo": {"status": "available"}}},
    ) is False


def test_owner_remote_task_without_runner_still_requires_default_mimo_runner():
    control = load_module(ROOT / "ops" / "factory_control.py")
    task = control.normalize_task({
        "kind": "owner_remote_task",
        "required_capability": "generic_implementation",
    })

    assert control.effective_task_runner(task) == "mimo"
    assert control.compatible(
        task,
        "mimo-node",
        ["generic_implementation", "runner:mimo"],
        {"runners": {"mimo": {"status": "available"}}},
    ) is True
    assert control.compatible(
        task,
        "generic-only",
        ["generic_implementation"],
        {"runners": {}},
    ) is False


def test_runner_status_available_without_capability_does_not_satisfy_runner_route():
    control = load_module(ROOT / "ops" / "factory_control.py")
    task = control.normalize_task({
        "kind": "owner_remote_task",
        "runner": "codex",
        "required_capability": "generic_implementation",
    })

    assert control.compatible(
        task,
        "runner-status-node",
        ["generic_implementation"],
        {"runners": {"codex": {"status": "available"}}},
    ) is False


def test_target_node_mimo_pool_task_only_leases_to_selected_pool_backing_node():
    control = load_module(ROOT / "ops" / "factory_control.py")
    task = control.normalize_task({
        "kind": "owner_remote_task",
        "runner": "codex",
        "required_capability": "generic_implementation",
        "target_node": "mesh-agent-20",
        "target_pool": ["mesh-agent-20-mimo-pool-01"],
    })

    assert control.compatible(
        task,
        "mesh-agent-20",
        ["generic_implementation", "runner:codex"],
        {"runners": {"codex": {"status": "available"}}},
    ) is True
    assert control.compatible(
        task,
        "mesh-agent-14",
        ["generic_implementation", "runner:codex"],
        {"runners": {"codex": {"status": "available"}}},
    ) is False


def test_filesystem_namespace_aggregates_node_manifests_without_raw_paths_by_default():
    control = load_module(ROOT / "ops" / "factory_control.py")
    now = datetime.now(timezone.utc)
    namespace = control.filesystem_namespace([
        {
            "node_id": "server-kfrm",
            "health": "online",
            "heartbeat_at": now.isoformat(),
            "filesystem": {
                "mode": "mesh_api_namespace",
                "namespace_prefix": "/kolibri/nodes/server-kfrm",
                "write_policy": "node-local writes only; no shared writable root disk; shared roots require leases",
                "roots": [
                    {
                        "name": "owner-project",
                        "namespace": "/kolibri/nodes/server-kfrm/owner-project",
                        "path": "/srv/kolibri-ai-platform",
                        "purpose": "owner project workspace",
                        "exists": True,
                        "writable": True,
                        "disk": {"total": 100, "used": 40, "free": 60},
                    },
                    {
                        "name": "artifacts",
                        "namespace": "/kolibri/nodes/server-kfrm/artifacts",
                        "path": "/var/lib/kolibri-agent/artifacts",
                        "purpose": "task logs and structured results",
                        "exists": True,
                        "writable": True,
                    },
                ],
            },
        }
    ])

    assert namespace["metadata_only"] is True
    assert namespace["local_paths_included"] is False
    assert namespace["namespace_prefix"] == "/kolibri/nodes"
    assert namespace["counts"] == {
        "nodes_total": 1,
        "nodes_with_filesystem": 1,
        "nodes_missing_filesystem": 0,
        "roots_total": 2,
        "writable_roots": 2,
    }
    assert namespace["nodes"][0]["namespace_prefix"] == "/kolibri/nodes/server-kfrm"
    assert namespace["nodes"][0]["roots"][0]["namespace"] == "/kolibri/nodes/server-kfrm/owner-project"
    assert "path" not in namespace["nodes"][0]["roots"][0]
    assert namespace["roots"][0]["node_id"] == "server-kfrm"
    assert namespace["repair_tasks"] == []


def test_filesystem_namespace_can_include_paths_for_authenticated_diagnostics():
    control = load_module(ROOT / "ops" / "factory_control.py")
    namespace = control.filesystem_namespace([
        {
            "node_id": "server-kfrm",
            "health": "online",
            "heartbeat_at": datetime.now(timezone.utc).isoformat(),
            "filesystem": {
                "namespace_prefix": "/kolibri/nodes/server-kfrm",
                "roots": [
                    {
                        "name": "owner-project",
                        "path": "/srv/kolibri-ai-platform",
                        "exists": True,
                        "writable": True,
                    }
                ],
            },
        }
    ], include_paths=True)

    assert namespace["local_paths_included"] is True
    assert namespace["nodes"][0]["roots"][0]["path"] == "/srv/kolibri-ai-platform"


def test_filesystem_namespace_reports_repair_task_for_missing_manifest():
    control = load_module(ROOT / "ops" / "factory_control.py")
    namespace = control.filesystem_namespace([
        {
            "node_id": "legacy-worker",
            "health": "online",
            "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        }
    ])

    assert namespace["counts"]["nodes_missing_filesystem"] == 1
    assert namespace["nodes"][0]["missing_manifest"] is True
    assert namespace["nodes"][0]["namespace_prefix"] == "/kolibri/nodes/legacy-worker"
    assert namespace["repair_tasks"] == [
        {
            "kind": "repair_node_filesystem_manifest",
            "node_id": "legacy-worker",
            "action": "restart or upgrade Agent Host so heartbeat includes filesystem.namespace_prefix and roots",
        }
    ]


def test_terminal_runner_contract_failure_creates_supported_auto_repair_task():
    control = load_module(ROOT / "ops" / "factory_control.py")
    created = []

    def fake_create_task(envelope):
        created.append(envelope)
        return control.normalize_task(envelope)

    control.create_task = fake_create_task
    task = control.normalize_task({
        "task_id": "P1_REMOTE_MIMO_POOL_NODE_BOOTSTRAP_AND_DIRECTOR_INTEGRATION_2026_07_02",
        "kind": "owner_remote_task",
        "required_capability": "generic_implementation",
    })
    task["lease_owner"] = "mesh-agent-20:agent-host-mesh-agent-20"
    body = {
        "error_type": "runner_contract_blocked",
        "error": "required_artifacts_missing",
        "result_reference": "docs/agent/runs/source/result.json",
        "result": {
            "status": "blocked",
            "blocked_reason": "required_artifacts_missing: docs/agent/MISSING.md",
            "required_artifacts_missing": ["docs/agent/MISSING.md"],
        },
        "retry": False,
    }

    repair = control.create_failure_repair_task(task, body)

    assert repair is not None
    assert len(created) == 1
    envelope = created[0]
    assert envelope["kind"] == "owner_remote_task"
    assert envelope["source"] == "control_plane_auto_repair"
    assert envelope["auto_repair"] is True
    assert envelope["repair_for_task_id"] == task["task_id"]
    assert envelope["target_node"] == "mesh-agent-20"
    assert envelope["required_capability"] == "generic_implementation"
    assert envelope["runner"] == "mimo"
    assert envelope["max_retries"] == 1
    assert envelope["repair"]["kind"] == "repair_required_artifacts"
    assert envelope["repair"]["required_artifacts_missing"] == ["docs/agent/MISSING.md"]
    assert envelope["control_center"]["surface"] == ["incidents", "tasks"]
    assert "docs/agent/MISSING.md" in envelope["acceptance"][1]
    assert task["repair_task_id"] == repair["task_id"]
    assert task["repair_task"]["kind"] == "repair_required_artifacts"


def test_auto_repair_task_failure_does_not_create_repair_loop():
    control = load_module(ROOT / "ops" / "factory_control.py")

    def fail_create_task(_envelope):
        raise AssertionError("repair task should not create another repair task")

    control.create_task = fail_create_task
    task = control.normalize_task({
        "task_id": "SOURCE-REPAIR-RUNNER_CONTRACT_BLOCKED",
        "kind": "owner_remote_task",
        "auto_repair": True,
        "repair_for_task_id": "SOURCE",
    })

    repair = control.create_failure_repair_task(task, {
        "error_type": "runner_contract_blocked",
        "error": "required_artifacts_missing",
        "retry": False,
    })

    assert repair is None
    assert "repair_task_id" not in task
