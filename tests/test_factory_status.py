from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from factory_status import build_factory_status, build_factory_status_from_summary


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
    assert "Свежие" in app_source
    assert "Деградируют" in app_source
    assert "Устарели" in app_source


def test_build_factory_status_from_summary_normalizes_fleet_data():
    now = datetime.now(timezone.utc)
    raw_nodes = [
        {
            "node_id": "primary-candidate",
            "health": "online",
            "freshness": "fresh",
            "heartbeat_age_seconds": 5,
            "capabilities": ["primary", "implementation"],
            "runners": {},
            "draining": False,
        },
        {
            "node_id": "new",
            "health": "stale",
            "freshness": "stale",
            "heartbeat_age_seconds": 120,
            "capabilities": ["review"],
            "runners": {},
            "draining": False,
        },
    ]
    task_states = {"running": 1, "queued": 2, "completed": 5}
    result = build_factory_status_from_summary(raw_nodes, task_states, 3, {"status": "ok", "time": now.isoformat()})

    assert result["status"] == "online"
    assert result["total_nodes"] == 2
    assert result["online_nodes"] == 1
    assert result["fresh_nodes"] == 1
    assert result["stale_nodes"] == 1
    assert result["queue_size"] == 3
    assert result["task_states"] == {"running": 1, "queued": 2, "completed": 5}
    assert result["nodes"]["primary-candidate"]["role"] == "Директор"
    assert result["control_plane"]["status"] == "ok"


def test_build_factory_status_from_summary_returns_degraded_when_no_online():
    raw_nodes = [
        {
            "node_id": "stale-worker",
            "health": "stale",
            "freshness": "stale",
            "heartbeat_age_seconds": 120,
            "capabilities": ["implementation"],
            "runners": {},
            "draining": False,
        },
    ]
    result = build_factory_status_from_summary(raw_nodes, {}, 0, {"status": "ok"})
    assert result["status"] == "degraded"
    assert result["online_nodes"] == 0
