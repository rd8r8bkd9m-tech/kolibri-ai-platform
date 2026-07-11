from __future__ import annotations

import sys
import asyncio
from pathlib import Path
from datetime import datetime, timedelta, timezone

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import factory_status
from factory_status import build_factory_status


def test_control_plane_v1_url_accepts_root_and_v1(monkeypatch):
    monkeypatch.setattr(factory_status, "CONTROL_PLANE_URL", "http://home-control.kolibri.internal:9101")
    assert factory_status._control_plane_v1_url("/health") == "http://home-control.kolibri.internal:9101/v1/health"
    monkeypatch.setattr(factory_status, "CONTROL_PLANE_URL", "http://home-control.kolibri.internal:9101/v1")
    assert factory_status._control_plane_v1_url("/nodes") == "http://home-control.kolibri.internal:9101/v1/nodes"


def test_default_never_invents_loopback_control_plane_authority(monkeypatch):
    assert factory_status.CONTROL_PLANE_URL != "http://127.0.0.1:9101"
    monkeypatch.setattr(factory_status, "CONTROL_PLANE_URL", None)
    with pytest.raises(RuntimeError, match="canonical_home_control_plane_unresolved"):
        factory_status._control_plane_v1_url("/health")


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


def test_factory_status_fails_closed_when_home_tasks_api_fails(monkeypatch):
    monkeypatch.setattr(factory_status, "CONTROL_PLANE_URL", "http://home-control.kolibri.internal:9101")

    class Response:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("home unavailable", request=None, response=None)

        def json(self):
            return self._payload

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            if url.endswith("/tasks"):
                return Response(503, {})
            return Response(200, {"status": "ok"} if url.endswith("/health") else {"nodes": []})

    monkeypatch.setattr(factory_status.httpx, "AsyncClient", lambda **kwargs: Client())
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(factory_status.fetch_factory_status())
