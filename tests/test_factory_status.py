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
                "region": "eu-central",
                "provider": "hetzner",
                "cluster": "control",
                "cell": "core-a",
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
    result = build_factory_status(
        payload,
        {
            "tasks": [
                {"task_id": "P0_REPAIR_RUNNER", "state": "running", "kind": "runner_repair", "node_id": "primary-candidate"},
                {
                    "task_id": "P0_AUTH_BLOCK",
                    "state": "auth_failed",
                    "result": {"blocked_reason": "runner_auth_blocked"},
                    "agent_id": "agent-host-primary",
                },
            ]
        },
        {"status": "ok", "queue_backend": "redis", "time": now.isoformat(), "telegram_ha": {"primary": "active", "standby": "ready"}},
    )

    assert result["status"] == "online"
    assert result["total_nodes"] == 2
    assert result["online_nodes"] == 1
    assert result["fresh_nodes"] == 1
    assert result["degraded_nodes"] == 0
    assert result["stale_nodes"] == 1
    assert result["offline_nodes"] == 1
    assert result["queue_size"] == 1
    assert result["nodes"]["primary-candidate"]["role"] == "Директор"
    assert result["nodes"]["primary-candidate"]["ram_total_gb"] > 0
    assert result["control_plane"]["status"] == "ok"
    assert result["topology_levels"] == ["global", "region", "provider", "cluster", "cell", "node", "agent", "task"]
    assert result["topology"]["rollup"]["total"] == 2
    assert result["topology"]["children"][0]["level"] == "region"
    assert result["active_repair_count"] == 1
    assert result["runner_auth_block_count"] == 1
    assert result["telegram_ha"]["status"] == "ready"
    assert result["owner_attention"]["runner_auth_blocks"] == 1


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
    assert result["node_freshness"] == {"fresh": 0, "degraded": 0, "stale": 1, "online": 0, "offline": 0, "total": 1}


def test_frontend_uses_live_factory_status_endpoint():
    app_source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.jsx").read_text(encoding="utf-8")

    assert "/api/factory/status" in app_source
    assert "/cluster/status" not in app_source
    assert "на базе 5 серверов" not in app_source
    assert "Kolibri AI Control Center" in app_source
    assert "Control Plane" in app_source
    assert "Owner Attention" in app_source
    assert "topology" in app_source
    assert "provider → cluster → cell" in app_source
    assert "Свежие" in app_source
    assert "Деградируют" in app_source
    assert "Устарели" in app_source
