from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import factory_status
from factory_status import build_factory_status


def test_default_control_plane_url_matches_secondary_control_plane():
    assert factory_status.CONTROL_PLANE_URL == "http://10.99.0.2:9101"


def test_control_plane_v1_url_accepts_root_and_v1(monkeypatch):
    monkeypatch.setattr(factory_status, "CONTROL_PLANE_URL", "http://control.kolibri.internal:9101")
    assert factory_status._control_plane_v1_url("/health") == "http://control.kolibri.internal:9101/v1/health"
    monkeypatch.setattr(factory_status, "CONTROL_PLANE_URL", "http://control.kolibri.internal:9101/v1")
    assert factory_status._control_plane_v1_url("/nodes") == "http://control.kolibri.internal:9101/v1/nodes"


def test_queue_size_falls_back_to_health_payload_when_tasks_are_skipped():
    status = build_factory_status(
        {"nodes": [{"node_id": "primary-candidate", "health": "online", "capabilities": ["primary"]}]},
        {"tasks": []},
        {"status": "ok", "queue": 7, "queue_backend": "redis"},
    )
    assert status["queue_size"] == 7
    assert status["online_nodes"] == 1


def test_fetch_factory_status_disables_proxy_env(monkeypatch):
    calls = []
    urls = []

    class Response:
        def __init__(self, url):
            self.url = url
            self.status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            if self.url.endswith("/health"):
                return {"status": "ok", "redis": "PONG", "queue_backend": "redis"}
            if self.url.endswith("/nodes"):
                return {"nodes": [{"node_id": "new", "health": "online", "capabilities": ["review"]}]}
            return {"tasks": []}

    class Client:
        def __init__(self, *args, **kwargs):
            calls.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            urls.append(url)
            return Response(url)

    monkeypatch.setattr(factory_status.httpx, "AsyncClient", Client)
    status = asyncio.run(factory_status.fetch_factory_status())

    assert status["control_plane"]["status"] == "ok"
    assert calls
    assert all(call.get("trust_env") is False for call in calls)
    assert any(url.endswith("/tasks?summary=1&compact=1") for url in urls)
