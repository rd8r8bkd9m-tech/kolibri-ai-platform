from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import factory_status
from factory_status import build_factory_status


def test_configured_control_plane_urls_include_local_mesh_fallback(monkeypatch):
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URLS", raising=False)
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URL", raising=False)
    urls = factory_status._configured_control_plane_urls()

    assert urls[0] == "http://10.99.0.2:9101"
    assert "http://control.kolibri.internal:9101" in urls


def test_configured_control_plane_urls_honor_explicit_primary(monkeypatch):
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URLS", raising=False)
    monkeypatch.setenv("KOLIBRI_FACTORY_CONTROL_URL", "http://control.kolibri.internal:9101")

    assert factory_status._configured_control_plane_urls()[0] == "http://control.kolibri.internal:9101"


def test_configured_control_plane_urls_can_be_overridden(monkeypatch):
    monkeypatch.setenv("KOLIBRI_FACTORY_CONTROL_URLS", "http://one:9101, http://two:9101, http://one:9101")

    assert factory_status._configured_control_plane_urls() == ["http://one:9101", "http://two:9101"]


def test_control_plane_v1_url_accepts_root_and_v1(monkeypatch):
    monkeypatch.setattr(factory_status, "CONTROL_PLANE_URL", "http://control.kolibri.internal:9101")
    assert factory_status._control_plane_v1_url("/health") == "http://control.kolibri.internal:9101/v1/health"
    monkeypatch.setattr(factory_status, "CONTROL_PLANE_URL", "http://control.kolibri.internal:9101/v1")
    assert factory_status._control_plane_v1_url("/nodes") == "http://control.kolibri.internal:9101/v1/nodes"
    assert factory_status._control_plane_v1_url("/nodes", "http://10.99.0.2:9101") == "http://10.99.0.2:9101/v1/nodes"


def test_queue_size_falls_back_to_health_payload_when_tasks_are_skipped():
    status = build_factory_status(
        {"nodes": [{"node_id": "primary-candidate", "health": "online", "capabilities": ["primary"]}]},
        {"tasks": []},
        {"status": "ok", "queue": 7, "queue_backend": "redis"},
    )
    assert status["queue_size"] == 7
    assert status["online_nodes"] == 1
