import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_steward():
    spec = importlib.util.spec_from_file_location("kfm_queue_steward", ROOT / "ops" / "kfm_queue_steward.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_control_urls_prefers_url_list(monkeypatch):
    steward = load_steward()
    monkeypatch.setenv("KOLIBRI_FACTORY_CONTROL_URLS", "http://a:9101, http://b:9101/")

    assert steward.control_urls() == ["http://a:9101", "http://b:9101"]


def test_select_control_plane_falls_back(monkeypatch):
    steward = load_steward()
    calls = []

    def fake_probe(url, path="/v1/health", timeout=4):
        calls.append(url)
        if url == "http://bad:9101":
            return steward.ControlProbe(url, path, False, None, 2000, "timed out"), None
        return steward.ControlProbe(url, path, True, 200, 12, "ok"), {"redis": "PONG"}

    monkeypatch.setattr(steward, "probe_control_plane", fake_probe)
    selection = steward.select_control_plane(["http://bad:9101", "http://ok:9101"])

    assert selection.control_plane_used == "http://ok:9101"
    assert len(selection.failed_candidates) == 1
    assert calls == ["http://bad:9101", "http://ok:9101"]


def test_unavailable_report_explains_none_is_not_zero():
    steward = load_steward()
    status = {
        "status": "control_plane_unavailable",
        "failed_candidates": [
            steward.ControlProbe("http://10.99.0.2:9101", "/v1/health", False, None, 4000, "timed out").__dict__
        ],
    }

    text = steward.format_owner_report(status)

    assert "не удалось проверить очередь" in text
    assert "Это не нули" in text
    assert "None" not in text
    assert "{" not in text


def test_success_report_uses_human_labels_not_raw_json():
    steward = load_steward()
    text = steward.format_owner_report({
        "status": "diagnosed",
        "control_plane_used": "http://10.99.0.1:9101",
        "redis": "PONG",
        "queue_seen": 18,
        "expired_leases": 0,
        "stuck_heartbeat_tasks": 0,
    })

    assert text.startswith("✅ Kolibri Lease Watchdog")
    assert "Control Plane: http://10.99.0.1:9101" in text
    assert "Queue: 18" in text
    assert "{" not in text


def test_run_unavailable_writes_clear_status(monkeypatch, tmp_path):
    steward = load_steward()
    monkeypatch.setattr(steward, "STATE_DIR", tmp_path)
    monkeypatch.setattr(steward, "LATEST", tmp_path / "latest.json")
    monkeypatch.setattr(
        steward,
        "select_control_plane",
        lambda: steward.ControlSelection(
            None,
            [steward.ControlProbe("http://bad:9101", "/v1/health", False, None, 1, "refused")],
            None,
        ),
    )

    status = steward.run(diagnose_only=True)

    assert status["status"] == "control_plane_unavailable"
    assert status["queue_seen"] is None
    assert (tmp_path / "latest.json").is_file()


def test_diagnose_only_does_not_submit_task(monkeypatch, tmp_path):
    steward = load_steward()
    monkeypatch.setattr(steward, "STATE_DIR", tmp_path)
    monkeypatch.setattr(steward, "LATEST", tmp_path / "latest.json")
    monkeypatch.setattr(
        steward,
        "select_control_plane",
        lambda: steward.ControlSelection("http://ok:9101", [], {"redis": "PONG"}),
    )
    calls = []

    def fake_request(base_url, path, method="GET", body=None, timeout=4):
        calls.append((method, path))
        if path == "/v1/tasks/queue/diagnostics":
            return {"expired_leases": 0, "stuck_heartbeat_tasks": 0}
        if path == "/v1/tasks":
            return {"tasks": [{"task_id": "T1", "state": "queued", "required_capability": "read_only_probe"}]}
        return {"nodes": []}

    monkeypatch.setattr(steward, "request_json", fake_request)
    status = steward.run(diagnose_only=True)

    assert status["status"] == "diagnosed"
    assert ("POST", "/v1/tasks") not in calls
