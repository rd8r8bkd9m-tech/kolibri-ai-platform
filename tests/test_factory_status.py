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
    assert result["nodes"]["primary-candidate"]["role"] == "Инженер"
    assert result["nodes"]["primary-candidate"]["ram_total_gb"] > 0
    assert result["control_plane"]["status"] == "ok"


def test_only_home_is_presented_as_control_plane():
    now = datetime.now(timezone.utc)
    result = build_factory_status(
        {
            "nodes": [
                {
                    "node_id": "home",
                    "role": "control_plane",
                    "health": "online",
                    "heartbeat_at": now.isoformat(),
                },
                {
                    "node_id": "main",
                    "role": "control_plane",
                    "health": "online",
                    "heartbeat_at": now.isoformat(),
                    "capabilities": ["implementation"],
                },
            ]
        },
        {"tasks": []},
        {"status": "ok", "time": now.isoformat()},
    )

    assert result["nodes"]["home"]["role"] == "Control Plane"
    assert result["nodes"]["main"]["role"] == "Worker"


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


def test_factory_status_uses_canonical_membership_and_exposes_quarantine_counts():
    result = build_factory_status(
        {
            "scope": "active",
            "membership": {
                "canonical_total": 21,
                "registered_total": 20,
                "missing_total": 1,
                "historical_total": 31,
            },
            "nodes": [
                {
                    "node_id": "worker-20",
                    "mesh_ip": "10.99.0.21",
                    "health": "quarantined",
                    "reported_health": "missing",
                    "freshness": "stale",
                    "registered": False,
                    "schedulable": False,
                    "lifecycle": "quarantined",
                    "membership_scope": "active",
                    "membership_state": "missing_agent_host_registration",
                }
            ],
        },
        {"tasks": []},
        {"status": "ok"},
    )

    assert result["total_nodes"] == 1
    assert result["quarantined_nodes"] == 1
    assert result["historical_nodes"] == 31
    assert result["nodes"]["worker-20"]["status"] == "quarantined"
    assert result["nodes"]["worker-20"]["ip"] == "10.99.0.21"
    assert result["membership"]["canonical_total"] == 21


def test_frontend_uses_live_factory_status_endpoint():
    frontend = Path(__file__).resolve().parents[1] / "frontend" / "src"
    app_source = (frontend / "App.jsx").read_text(encoding="utf-8")
    control_source = (frontend / "control" / "ControlShell.jsx").read_text(
        encoding="utf-8"
    )
    api_source = (frontend / "runtime" / "kolibriApi.js").read_text(encoding="utf-8")

    assert "/api/factory/status" in api_source
    assert "/cluster/status" not in app_source + control_source + api_source
    assert "на базе 5 серверов" not in app_source + control_source
    assert "<ControlShell />" in app_source
    assert "loadControlSnapshot" in control_source
    assert "Фактическое состояние" in control_source
    assert "без mock-значений" in control_source
    assert "Degraded" in control_source
