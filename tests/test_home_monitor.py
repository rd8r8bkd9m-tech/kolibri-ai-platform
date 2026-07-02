from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from factory_status import build_factory_status
from home_monitor import build_home_monitor_status, build_wallboard, HOME_MONITOR_PREFERENCES, WALLBOARD_STATUS_LABELS, TASK_STATE_LABELS


def _make_factory_status():
    now = datetime.now(timezone.utc)
    return build_factory_status(
        {
            "nodes": [
                {
                    "node_id": "home",
                    "hostname": "plastilin",
                    "health": "online",
                    "heartbeat_at": (now - timedelta(seconds=3)).isoformat(),
                    "capabilities": ["fabric_api", "fallback_relay"],
                    "cpu": 4,
                    "ram": {"MemTotal": "8192000 kB", "MemAvailable": "6144000 kB"},
                    "disk": {"free": 50000000000, "total": 100000000000},
                },
                {
                    "node_id": "9fts",
                    "hostname": "engine",
                    "health": "online",
                    "heartbeat_at": (now - timedelta(seconds=5)).isoformat(),
                    "capabilities": ["implementation", "runner:mimo"],
                    "cpu": 8,
                    "ram": {"MemTotal": "16384000 kB", "MemAvailable": "12288000 kB"},
                    "disk": {"free": 80000000000, "total": 200000000000},
                },
            ]
        },
        {"tasks": [{"state": "queued"}, {"state": "running"}, {"state": "completed"}]},
        {"status": "ok", "queue_backend": "redis", "time": now.isoformat()},
    )


def test_build_home_monitor_status_fleet():
    factory_status = _make_factory_status()
    monitor = build_home_monitor_status(factory_status)
    assert monitor["status"] == "online"
    assert monitor["fleet"]["total_nodes"] == 2
    assert monitor["fleet"]["fresh_nodes"] == 2
    assert monitor["fleet"]["free_ram_gb"] > 0
    assert len(monitor["nodes"]) == 2


def test_build_home_monitor_status_tasks():
    factory_status = _make_factory_status()
    monitor = build_home_monitor_status(factory_status)
    assert monitor["tasks"]["total"] == 3
    assert monitor["tasks"]["active"] == 2
    assert monitor["tasks"]["completed"] == 1
    assert monitor["tasks"]["states"]["queued"] == 1
    assert monitor["tasks"]["states"]["running"] == 1
    assert monitor["tasks"]["states"]["completed"] == 1


def test_build_home_monitor_status_preferences():
    factory_status = _make_factory_status()
    monitor = build_home_monitor_status(factory_status)
    prefs = monitor["preferences"]
    assert prefs["ai_runner"] == "mimo-auto"
    assert prefs["owner_language"] == "ru"
    assert prefs["default_task_runner"] == "mimo"
    assert prefs["auto_refresh_seconds"] == 15


def test_build_home_monitor_status_node_labels():
    factory_status = _make_factory_status()
    monitor = build_home_monitor_status(factory_status)
    home_node = next(n for n in monitor["nodes"] if n["node_id"] == "home")
    assert home_node["status_label"] == "Онлайн"
    assert home_node["name"] == "Связной"
    engineer_node = next(n for n in monitor["nodes"] if n["node_id"] == "9fts")
    assert engineer_node["status_label"] == "Онлайн"
    assert engineer_node["name"] == "Инженер"


def test_build_wallboard_tasks_sorted():
    factory_status = _make_factory_status()
    tasks = [
        {"task_id": "T1", "kind": "owner_remote_task", "state": "completed", "created_at": "2026-07-02T10:00:00Z", "updated_at": "2026-07-02T10:30:00Z"},
        {"task_id": "T2", "kind": "impl_factory_smoke", "state": "running", "lease_owner": "9fts:host", "created_at": "2026-07-02T11:00:00Z", "updated_at": "2026-07-02T11:05:00Z"},
        {"task_id": "T3", "kind": "review_pr", "state": "queued", "created_at": "2026-07-02T11:30:00Z", "updated_at": "2026-07-02T11:30:00Z"},
    ]
    wallboard = build_wallboard(factory_status, tasks)
    wb_tasks = wallboard["wallboard"]["tasks"]
    assert wb_tasks[0]["task_id"] == "T3"
    assert wb_tasks[0]["state"] == "queued"
    assert wb_tasks[1]["task_id"] == "T2"
    assert wb_tasks[1]["state"] == "running"
    assert wb_tasks[2]["task_id"] == "T1"
    assert wb_tasks[2]["state"] == "completed"
    assert wallboard["wallboard"]["task_count"] == 3


def test_wallboard_task_summary_fields():
    factory_status = _make_factory_status()
    task = {
        "task_id": "TGAPP-abc123",
        "kind": "owner_remote_task",
        "state": "running",
        "attempt": 1,
        "lease_owner": "9fts:mimo-agent",
        "created_at": "2026-07-02T10:00:00Z",
        "updated_at": "2026-07-02T10:15:00Z",
        "envelope": {"objective": "Проверь CI"},
        "error_type": None,
    }
    wallboard = build_wallboard(factory_status, [task])
    summary = wallboard["wallboard"]["tasks"][0]
    assert summary["task_id"] == "TGAPP-abc123"
    assert summary["node_id"] == "9fts"
    assert summary["objective"] == "Проверь CI"
    assert summary["state_label"] == "Выполняется"


def test_task_state_labels_are_russian():
    assert TASK_STATE_LABELS["queued"] == "В очереди"
    assert TASK_STATE_LABELS["running"] == "Выполняется"
    assert TASK_STATE_LABELS["completed"] == "Завершена"
    assert TASK_STATE_LABELS["failed"] == "Ошибка"


def test_wallboard_status_labels_are_russian():
    assert WALLBOARD_STATUS_LABELS["fresh"] == "Онлайн"
    assert WALLBOARD_STATUS_LABELS["degraded"] == "Деградация"
    assert WALLBOARD_STATUS_LABELS["stale"] == "Устарел"


def test_monitor_preferences_mimo_auto():
    assert HOME_MONITOR_PREFERENCES["ai_runner"] == "mimo-auto"
    assert HOME_MONITOR_PREFERENCES["default_task_runner"] == "mimo"


def test_home_monitor_endpoints_exist_in_backend():
    backend_source = (Path(__file__).resolve().parents[1] / "backend" / "main.py").read_text(encoding="utf-8")
    assert "/api/home/monitor" in backend_source
    assert "/api/home/wallboard" in backend_source
    assert "fetch_home_monitor" in backend_source
    assert "fetch_wallboard" in backend_source


def test_monitor_tab_exists_in_frontend():
    app_source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.jsx").read_text(encoding="utf-8")
    assert "Диспетчер" in app_source
    assert "MonitorView" in app_source
    assert "/api/home/monitor" in app_source
    assert "monitor" in app_source
