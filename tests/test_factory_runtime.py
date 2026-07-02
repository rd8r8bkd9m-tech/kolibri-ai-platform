import importlib.util
from pathlib import Path
from datetime import datetime, timedelta, timezone


ROOT = Path(__file__).resolve().parents[1]


def load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_dispatcher_exposes_required_commands():
    dispatch = (ROOT / "ops" / "kolibri-dispatch").read_text(encoding="utf-8")
    for command in ["doctor", "nodes", "submit", "status", "backlog-audit", "collect", "cancel", "drain"]:
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


def test_backlog_policy_marks_github_clone_failures_retryable_after_repair():
    control = load_module(ROOT / "ops" / "factory_control.py")
    audit = control.backlog_policy([
        {
            "task_id": "CLONE-1",
            "state": "failed",
            "attempt": 1,
            "max_retries": 1,
            "lease_owner": "qjns:agent-host-qjns",
            "error_type": "review_clone_auth_failed",
            "error": "git clone failed without printing credentials",
            "envelope": {"target_node": "qjns", "kind": "review_pr"},
        }
    ])

    entry = audit["tasks"][0]
    assert entry["safe_action"] == control.POLICY_REQUEUE_AFTER_GITHUB_CLONE_REPAIR
    assert entry["safe_to_retry_after_github_clone_repair"] is True
    assert audit["safe_to_retry_after_github_clone_repair"] == ["CLONE-1"]
    assert entry["node"] == "qjns"


def test_backlog_policy_supersedes_failed_tasks_with_useful_artifacts():
    control = load_module(ROOT / "ops" / "factory_control.py")
    audit = control.backlog_policy([
        {
            "task_id": "ARTIFACT-1",
            "state": "failed",
            "attempt": 1,
            "max_retries": 3,
            "result_reference": "/var/lib/kolibri-agent/artifacts/ARTIFACT-1/result.json",
            "result": {"pull_request_url": "https://example.invalid/pr/1"},
            "envelope": {"target_node": "primary-candidate"},
        }
    ])

    entry = audit["tasks"][0]
    assert entry["safe_action"] == control.POLICY_SUPERSEDE
    assert entry["reason"] == "failed_task_has_useful_artifacts_use_followup_not_blind_retry"
    assert entry["safe_to_retry_after_github_clone_repair"] is False


def test_backlog_policy_requeues_expired_lease_debt_with_budget_only():
    control = load_module(ROOT / "ops" / "factory_control.py")
    current = 1000.0
    audit = control.backlog_policy(
        [
            {
                "task_id": "LEASE-1",
                "state": "running",
                "attempt": 1,
                "max_retries": 2,
                "lease_owner": "primary-candidate:agent-host-primary",
                "lease_until": current - 45,
            },
            {
                "task_id": "LEASE-2",
                "state": "leased",
                "attempt": 2,
                "max_retries": 2,
                "lease_owner": "main:agent-host-main",
                "lease_until": current - 60,
            },
        ],
        current=current,
    )

    by_id = {entry["task_id"]: entry for entry in audit["tasks"]}
    assert by_id["LEASE-1"]["safe_action"] == control.POLICY_REQUEUE_NOW
    assert by_id["LEASE-1"]["lease_debt_seconds"] == 45
    assert by_id["LEASE-2"]["safe_action"] == control.POLICY_BLOCKED
    assert by_id["LEASE-2"]["reason"] == "expired_lease_retry_budget_exhausted"
