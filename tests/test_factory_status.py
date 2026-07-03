from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from factory_status import build_factory_status, build_fleet_summary_snapshot


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


def test_fleet_summary_snapshot_returns_nonzero_nodes_with_counts_and_queue():
    now = datetime.now(timezone.utc)
    nodes_payload = {
        "nodes": [
            {
                "node_id": "primary-candidate",
                "hostname": "kolibri",
                "health": "online",
                "heartbeat_at": (now - timedelta(seconds=5)).isoformat(),
                "capabilities": ["primary", "implementation"],
                "cpu": 12,
                "ram": {"MemTotal": "16384000 kB", "MemAvailable": "14000000 kB"},
                "disk": {"free": 50000000000, "total": 100000000000},
            },
            {
                "node_id": "9fts",
                "health": "online",
                "heartbeat_at": (now - timedelta(seconds=10)).isoformat(),
                "capabilities": ["implementation"],
                "cpu": 5,
                "ram": {"MemTotal": "8192000 kB", "MemAvailable": "6000000 kB"},
                "disk": {"free": 30000000000, "total": 60000000000},
            },
        ]
    }
    tasks_payload = {
        "tasks": [
            {"task_id": "T1", "state": "queued", "kind": "impl", "runner": "mimo"},
            {"task_id": "T2", "state": "running", "kind": "review", "runner": "mimo"},
            {"task_id": "T3", "state": "completed", "kind": "impl", "runner": "mimo"},
        ]
    }
    health_payload = {"status": "ok", "queue_backend": "redis", "time": now.isoformat()}
    snapshot = build_fleet_summary_snapshot(nodes_payload, tasks_payload, health_payload)

    assert snapshot["snapshot"] is True
    assert snapshot["total_nodes"] == 2
    assert snapshot["online_nodes"] >= 1
    assert snapshot["total_nodes"] >= 2
    assert "task_states" in snapshot
    assert snapshot["task_states"]["queued"] == 1
    assert snapshot["task_states"]["running"] == 1
    assert snapshot["task_states"]["completed"] == 1
    assert snapshot["queue_size"] >= 2
    assert len(snapshot["task_queue"]) == 2
    assert snapshot["task_queue"][0]["state"] in {"queued", "running"}
    assert snapshot["free_ram_gb"] > 0
    assert snapshot["total_ram_gb"] > 0
    assert "nodes" in snapshot
    assert len(snapshot["nodes"]) == 2
    assert snapshot["node_freshness"]["total"] == 2
    assert snapshot["generated_at"]


def test_fleet_summary_snapshot_degraded_with_zero_tasks():
    now = datetime.now(timezone.utc)
    nodes_payload = {"nodes": [{"node_id": "only", "health": "offline", "capabilities": [], "ram": {}, "disk": {}}]}
    snapshot = build_fleet_summary_snapshot(nodes_payload, {"tasks": []}, {"status": "ok", "time": now.isoformat()})

    assert snapshot["snapshot"] is True
    assert snapshot["total_nodes"] == 1
    assert snapshot["task_queue"] == []
    assert snapshot["task_states"] == {}
    assert len(snapshot["nodes"]) == 1


def test_backend_main_exports_snapshot_endpoint():
    main_source = (Path(__file__).resolve().parents[1] / "backend" / "main.py").read_text(encoding="utf-8")
    assert "/api/snapshot" in main_source
    assert "fetch_fleet_summary_snapshot" in main_source
