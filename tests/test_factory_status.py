from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from factory_status import build_factory_status


def test_build_factory_status_normalizes_control_plane_nodes():
    now = datetime.now(timezone.utc)
    payload = {
        "nodes": [
            {
                "node_id": "primary-candidate",
                "hostname": "kolibri",
                "health": "online",
                "heartbeat_at": (now - timedelta(seconds=5)).isoformat(),
                "agent_id": "agent-host-primary",
                "pid": 120138,
                "capabilities": ["primary", "implementation", "review"],
                "cpu": 8,
                "ram": {"MemTotal": "12247028 kB", "MemAvailable": "11510364 kB"},
                "disk": {"free": 94581936128, "total": 105590231040},
            },
            {"node_id": "new", "health": "offline", "capabilities": ["review"], "ram": {}, "disk": {}},
        ]
    }
    result = build_factory_status(payload, {"tasks": [{"state": "queued"}, {"state": "running"}]}, {"status": "ok", "queue_backend": "redis", "time": now.isoformat()})

    assert result["status"] == "online"
    assert result["total_nodes"] == 2
    assert result["online_nodes"] == 1
    assert result["fresh_nodes"] == 1
    assert result["degraded_nodes"] == 0
    assert result["stale_nodes"] == 1
    assert result["queue_size"] == 2
    assert len(result["recent_tasks"]) == 2
    assert result["safe_actions"][0]["id"] == "refresh_status"
    assert result["nodes"]["primary-candidate"]["role"] == "Директор"
    assert result["nodes"]["primary-candidate"]["ram_total_gb"] > 0
    assert result["control_plane"]["status"] == "ok"


def test_stale_heartbeat_online_mismatch_is_not_counted_online():
    now = datetime.now(timezone.utc)
    result = build_factory_status(
        {
            "nodes": [
                {
                    "node_id": "stale-worker",
                    "health": "online",
                    "heartbeat_at": (now - timedelta(seconds=600)).isoformat(),
                    "capabilities": ["implementation"],
                }
            ]
        },
        {"tasks": []},
        {"status": "ok", "time": now.isoformat()},
    )

    node = result["nodes"]["stale-worker"]
    assert node["reported_health"] == "online"
    assert node["freshness"] == "stale"
    assert node["status"] == "stale"
    assert result["online_nodes"] == 0
    assert result["node_freshness"] == {"fresh": 0, "degraded": 0, "stale": 1, "online": 0, "total": 1}


def test_frontend_uses_live_factory_status_endpoint():
    app_source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.jsx").read_text(encoding="utf-8")

    assert "/api/factory/status" in app_source
    assert "/cluster/status" not in app_source
    assert "на базе 5 серверов" not in app_source
    assert "Фабрика Колибри" in app_source
    assert "Kolibri Factory" in app_source
    assert "launch_readiness_probe" in app_source
    assert "pull_requests" in app_source


def test_factory_status_extracts_dashboard_prs_and_blockers():
    now = datetime.now(timezone.utc)
    status = build_factory_status(
        {"nodes": [{"node_id": "9fts", "health": "online", "heartbeat_at": now.isoformat(), "capabilities": ["implementation"]}]},
        {
            "tasks": [
                {
                    "task_id": "TASK-1",
                    "state": "waiting_review",
                    "lease_owner": "9fts:agent",
                    "envelope": {"objective": "Implement dashboard"},
                    "result": {"pull_request_url": "https://github.com/example/repo/pull/1", "branch": "factory-dashboard"},
                    "updated_at": now.isoformat(),
                },
                {
                    "task_id": "TASK-2",
                    "state": "failed",
                    "error_type": "runner_auth_blocked",
                    "error": "runner token unavailable",
                    "envelope": {"objective": "Launch repair"},
                },
            ]
        },
        {"status": "ok", "time": now.isoformat()},
    )

    assert status["pull_requests"] == [
        {
            "task_id": "TASK-1",
            "title": "Implement dashboard",
            "url": "https://github.com/example/repo/pull/1",
            "branch": "factory-dashboard",
            "state": "waiting_review",
            "node": "9fts",
            "updated_at": now.isoformat(),
        }
    ]
    assert status["blockers"][0]["reason"] == "runner_auth_blocked"
    assert status["tasks"][1]["blocked"] is True
