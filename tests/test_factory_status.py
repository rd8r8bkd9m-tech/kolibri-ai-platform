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
    assert "Агенты онлайн" in app_source
    assert "Деградируют" in app_source
    assert "Живой пульт Home" in app_source
    assert "Блокеры" in app_source
    assert "Логи и артефакты" in app_source


def test_build_factory_status_normalizes_wallboard_payloads():
    now = datetime.now(timezone.utc)
    result = build_factory_status(
        {
            "nodes": [
                {
                    "node_id": "worker-a",
                    "health": "online",
                    "heartbeat_at": (now - timedelta(seconds=4)).isoformat(),
                    "capabilities": ["implementation"],
                }
            ]
        },
        {
            "tasks": [{"task_id": "P0", "state": "running", "goal": "Ship wallboard", "leased_by": "worker-a"}],
            "blockers": {"items": [{"id": "B1", "title": "Redis down", "severity": "high", "repair_command": "systemctl restart redis"}]},
            "prs": {"items": [{"number": 101, "title": "Wallboard UI", "state": "open", "checks": "pending"}]},
            "logs": {"events": [{"id": "L1", "level": "info", "source": "agent-host", "message": "lease renewed"}]},
        },
        {"status": "ok", "queue_backend": "redis", "redis": "ok", "time": now.isoformat()},
    )

    assert result["tasks"][0]["title"] == "Ship wallboard"
    assert result["tasks"][0]["assignee"] == "worker-a"
    assert result["blockers"][0]["title"] == "Redis down"
    assert result["blockers"][0]["repair"] == "systemctl restart redis"
    assert result["prs"][0]["number"] == 101
    assert result["logs"][0]["source"] == "agent-host"
    assert {item["name"] for item in result["server_health"]} >= {"Control Plane", "Redis", "Agent Host", "Frontend API"}
