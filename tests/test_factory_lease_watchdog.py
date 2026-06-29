import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_watchdog():
    spec = importlib.util.spec_from_file_location("factory_lease_watchdog", ROOT / "ops" / "factory_lease_watchdog.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_run_watchdog_calls_reap_and_sweep_without_rebuild_by_default(monkeypatch):
    watchdog = load_watchdog()
    calls = []

    def fake_call(control_url, method, path, body=None, timeout=20):
        calls.append((method, path, body, timeout))
        if path == "/v1/health":
            return {"status": "ok", "redis": "PONG", "queue_backend": "redis"}
        if path == "/v1/tasks/reap-expired":
            return {"task_total": 10, "lease_index_total": 1, "expired": 0, "requeued_total": 0, "dead_lettered_total": 0}
        if path == "/v1/tasks/sweep-stuck":
            return {"task_total": 10, "lease_index_total": 1, "stuck": 0, "requeued_total": 0, "dead_lettered_total": 0, "stale_after_seconds": 3600}
        raise AssertionError(path)

    monkeypatch.setattr(watchdog, "call_control", fake_call)

    report = watchdog.run_watchdog("http://control:9101", limit=50, stale_after_seconds=3600, timeout=7)

    assert [call[1] for call in calls] == ["/v1/health", "/v1/tasks/reap-expired", "/v1/tasks/sweep-stuck"]
    assert calls[1][2] == {"limit": 50}
    assert calls[2][2] == {"limit": 50, "stale_after_seconds": 3600}
    assert report["summary"]["status"] == "ok"
    assert report["summary"]["lease_index_total"] == 1
    assert report["summary"]["stuck"] == 0


def test_run_watchdog_can_rebuild_indexes_first(monkeypatch):
    watchdog = load_watchdog()
    calls = []

    def fake_call(control_url, method, path, body=None, timeout=20):
        calls.append(path)
        if path == "/v1/health":
            return {"status": "ok", "redis": "PONG", "queue_backend": "redis"}
        if path == "/v1/tasks/rebuild-indexes":
            return {"indexed": 690}
        if path == "/v1/tasks/reap-expired":
            return {"task_total": 690, "lease_index_total": 1, "expired": 0, "requeued_total": 0, "dead_lettered_total": 0}
        if path == "/v1/tasks/sweep-stuck":
            return {"task_total": 690, "lease_index_total": 1, "stuck": 0, "requeued_total": 0, "dead_lettered_total": 0, "stale_after_seconds": 3600}
        raise AssertionError(path)

    monkeypatch.setattr(watchdog, "call_control", fake_call)

    report = watchdog.run_watchdog("http://control:9101", limit=20, stale_after_seconds=3600, timeout=5, rebuild_indexes=True)

    assert calls == ["/v1/health", "/v1/tasks/rebuild-indexes", "/v1/tasks/reap-expired", "/v1/tasks/sweep-stuck"]
    assert report["summary"]["rebuild_indexed"] == 690


def test_write_reports_creates_latest_json_and_markdown(tmp_path):
    watchdog = load_watchdog()
    report = {
        "event": "factory_lease_watchdog",
        "control_url": "http://control:9101",
        "started_at": "2026-06-29T07:40:00+00:00",
        "finished_at": "2026-06-29T07:40:01+00:00",
        "summary": {"status": "ok", "task_total": 10, "lease_index_total": 1},
    }

    json_path, md_path = watchdog.write_reports(report, tmp_path)

    assert json.loads(json_path.read_text(encoding="utf-8"))["event"] == "factory_lease_watchdog"
    assert "# Kolibri Factory Lease Watchdog" in md_path.read_text(encoding="utf-8")
    assert json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))["summary"]["status"] == "ok"
    assert "Task total" in (tmp_path / "latest.md").read_text(encoding="utf-8")
