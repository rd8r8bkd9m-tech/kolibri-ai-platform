from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import factory_status
from factory_status import build_factory_status


def test_control_plane_v1_url_accepts_root_and_v1(monkeypatch):
    monkeypatch.setattr(factory_status, "CONTROL_PLANE_URL", "http://control.kolibri.internal:9101")
    assert factory_status._control_plane_v1_url("/health") == "http://control.kolibri.internal:9101/v1/health"
    monkeypatch.setattr(factory_status, "CONTROL_PLANE_URL", "http://control.kolibri.internal:9101/v1")
    assert factory_status._control_plane_v1_url("/nodes") == "http://control.kolibri.internal:9101/v1/nodes"


def test_queue_size_falls_back_to_health_payload_when_tasks_are_skipped():
    now = datetime.now(timezone.utc)
    status = build_factory_status(
        {"nodes": [{"node_id": "primary-candidate", "health": "online", "heartbeat_at": (now - timedelta(seconds=2)).isoformat(), "capabilities": ["primary"]}]},
        {"tasks": []},
        {"status": "ok", "queue": 7, "queue_backend": "redis", "time": now.isoformat()},
    )
    assert status["queue_size"] == 7
    assert status["online_nodes"] == 1
    assert status["node_freshness"]["fresh"] == 1
