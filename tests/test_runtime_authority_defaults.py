from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def load_routes_v1():
    spec = importlib.util.spec_from_file_location("runtime_authority_routes_v1", BACKEND / "routes_v1.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_factory_control():
    spec = importlib.util.spec_from_file_location("runtime_authority_factory_control", ROOT / "ops" / "factory_control.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_compatibility_swarm_status_uses_live_home_snapshot(monkeypatch):
    routes = load_routes_v1()

    async def snapshot():
        return {
            "status": "online",
            "total_nodes": 23,
            "online_nodes": 21,
            "fresh_nodes": 20,
            "degraded_nodes": 1,
            "stale_nodes": 2,
            "queue_size": 8,
        }

    monkeypatch.setattr(routes, "fetch_factory_status", snapshot)
    result = asyncio.run(routes.swarm_status())

    assert result == {
        "status": "online",
        "source": "control-plane/home",
        "nodes": 23,
        "online_nodes": 21,
        "fresh_nodes": 20,
        "degraded_nodes": 1,
        "stale_nodes": 2,
        "queue_size": 8,
    }


def test_compatibility_swarm_status_fails_closed_when_home_is_unavailable(monkeypatch):
    routes = load_routes_v1()

    async def unavailable():
        raise RuntimeError("do not expose transport detail")

    monkeypatch.setattr(routes, "fetch_factory_status", unavailable)
    response = asyncio.run(routes.swarm_status())

    assert response.status_code == 503
    assert json.loads(response.body) == {
        "status": "degraded",
        "source": "control-plane/home",
        "reason": "canonical_home_control_plane_unavailable",
    }


def test_active_compatibility_sources_have_no_static_legacy_fleet_claim():
    adapter = (BACKEND / "adapter.py").read_text(encoding="utf-8")
    routes = (BACKEND / "routes_v1.py").read_text(encoding="utf-8")

    assert '["main", "uiap", "qjns", "9fts"]' not in adapter
    assert '"nodes": 4' not in adapter
    assert '"nodes": 4' not in routes
    assert "fetch_factory_status" in adapter
    assert "fetch_factory_status" in routes


def test_review_task_uses_capability_scheduler_without_static_worker(monkeypatch):
    control = load_factory_control()
    captured = []

    def create_task(envelope):
        captured.append(envelope)
        return {"task_id": envelope["task_id"], "state": control.STATE_QUEUED, "envelope": envelope}

    monkeypatch.setattr(control, "create_task", create_task)
    monkeypatch.setattr(control, "save_task", lambda _task: None)
    review = control.create_review_task(
        {
            "task_id": "TASK-1",
            "envelope": {"create_review_on_complete": True, "base_ref": "origin/main"},
        },
        {"pull_request_url": "https://example.invalid/pull/1", "branch": "agent/task-1"},
    )

    assert review is not None
    assert captured[0]["required_capability"] == "review"
    assert "target_node" not in captured[0]
