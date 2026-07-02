from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops"))

from home_wallboard_status_ru import HttpProbe, render_status, summarize_nodes, summarize_tasks


def test_summarizes_control_plane_enveloped_nodes():
    payload = {
        "status": "completed",
        "data": {
            "nodes": [
                {"node_id": "home", "health": "online"},
                {"node_id": "agent-02", "health": "stale"},
            ]
        },
    }

    assert summarize_nodes(payload) == {"total": 2, "online": 1, "degraded": 1}


def test_summarizes_public_compatibility_status():
    payload = {
        "nodes": {"total": 3, "states": {"online": 2, "degraded": 1}},
        "tasks": {"total": 5, "queued": 2, "running": 1},
    }

    assert summarize_nodes(payload) == {"total": 3, "online": 2, "degraded": 1}
    assert summarize_tasks(payload) == {"total": 5, "queued": 2, "running": 1}


def test_summarizes_task_queue_when_task_details_are_empty():
    payload = {"queue": ["task-1", "task-2"], "tasks": []}

    assert summarize_tasks(payload) == {"total": 2, "queued": 2, "running": 0}


def test_render_status_is_russian_read_only_and_flags_public_visibility_gap():
    output = render_status(
        control_health=HttpProbe(
            url="http://control/v1/health",
            ok=True,
            status_code=200,
            data={"data": {"redis": "PONG"}},
        ),
        control_nodes=HttpProbe(
            url="http://control/v1/fleet/nodes",
            ok=True,
            status_code=200,
            data={"data": {"nodes": [{"node_id": "home", "health": "online"}]}},
        ),
        control_tasks=HttpProbe(
            url="http://control/v1/tasks",
            ok=True,
            status_code=200,
            data={"queue": ["task-1"], "tasks": []},
        ),
        public_status=HttpProbe(
            url="http://public/api/factory/status",
            ok=True,
            status_code=200,
            data={"product": "Колибри", "runtime": "compatibility_gateway", "nodes": {"total": 0}, "tasks": {"total": 0}},
        ),
        services=[{"Id": "kolibri-factory-control.service", "ActiveState": "active", "SubState": "running", "MainPID": "123"}],
        now=datetime(2026, 7, 2, 2, 50, tzinfo=timezone.utc),
    )

    assert "Колибри Фабрика — статус автопилота" in output
    assert "Режим: read-only" in output
    assert "без restart/start/stop" in output
    assert "Секреты не читаются" in output
    assert "Блокер видимости" in output
