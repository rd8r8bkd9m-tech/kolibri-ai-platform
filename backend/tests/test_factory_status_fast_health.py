from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import factory_status
from factory_status import build_factory_status, fetch_factory_status


def test_control_plane_v1_url_accepts_root_and_v1(monkeypatch):
    monkeypatch.setattr(factory_status, "CONTROL_PLANE_URL", "http://control.kolibri.internal:9101")
    assert factory_status._control_plane_v1_url("/health") == "http://control.kolibri.internal:9101/v1/health"
    monkeypatch.setattr(factory_status, "CONTROL_PLANE_URL", "http://control.kolibri.internal:9101/v1")
    assert factory_status._control_plane_v1_url("/nodes") == "http://control.kolibri.internal:9101/v1/nodes"


def test_control_plane_urls_are_ordered_and_deduplicated(monkeypatch):
    monkeypatch.setenv("KOLIBRI_FACTORY_CONTROL_URLS", "http://slow:9101, http://fast:9101;http://slow:9101")
    monkeypatch.setattr(factory_status, "CONTROL_PLANE_URL", "http://ignored:9101")
    monkeypatch.setattr(factory_status, "CONTROL_PLANE_FALLBACK_URLS", "http://fallback:9101")

    assert factory_status._control_plane_urls() == ["http://slow:9101", "http://fast:9101"]


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


def test_health_envelope_is_normalized_for_control_plane_status():
    now = datetime.now(timezone.utc)
    status = build_factory_status(
        {"nodes": []},
        {"tasks": []},
        {
            "status": "completed",
            "data": {
                "queue": 4,
                "queue_backend": "redis",
                "redis": "PONG",
                "time": now.isoformat(),
            },
        },
        "http://fast:9101",
    )

    assert status["control_plane"] == {
        "url": "http://fast:9101",
        "status": "ok",
        "queue_backend": "redis",
        "redis": "PONG",
    }
    assert status["queue_size"] == 4


def test_fetch_factory_status_falls_back_when_primary_times_out(monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    calls = []

    async def fake_fetch_required(base_url):
        calls.append(base_url)
        if base_url == "http://slow:9101":
            await asyncio.sleep(0)
            raise TimeoutError("primary timed out")
        return (
            {"status": "ok", "queue": 3, "queue_backend": "redis", "time": now},
            {
                "nodes": [
                    {
                        "node_id": "primary-candidate",
                        "health": "online",
                        "heartbeat_at": now,
                        "capabilities": ["primary"],
                    }
                ]
            },
        )

    async def fake_fetch_tasks(base_url):
        assert base_url == "http://fast:9101"
        return {"tasks": [{"state": "running"}]}

    monkeypatch.setenv("KOLIBRI_FACTORY_CONTROL_URLS", "http://slow:9101,http://fast:9101")
    monkeypatch.setattr(factory_status, "CONTROL_PLANE_FETCH_TASKS", True)
    monkeypatch.setattr(factory_status, "_fetch_required_status_payloads", fake_fetch_required)
    monkeypatch.setattr(factory_status, "_fetch_optional_tasks_payload", fake_fetch_tasks)

    status = asyncio.run(fetch_factory_status())

    assert calls == ["http://slow:9101", "http://fast:9101"]
    assert status["control_plane"]["url"] == "http://fast:9101"
    assert status["control_plane"]["status"] == "ok"
    assert status["queue_size"] == 1
    assert status["online_nodes"] == 1
