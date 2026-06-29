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

    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert written["event"] == "factory_lease_watchdog"
    assert written["rollup"]["runs_total"] == 1
    assert "# Kolibri Factory Lease Watchdog" in md_path.read_text(encoding="utf-8")
    assert json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))["summary"]["status"] == "ok"
    assert "Task total" in (tmp_path / "latest.md").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))["runs_total"] == 1
    assert "Runs total" in (tmp_path / "latest-summary.md").read_text(encoding="utf-8")


def test_update_rollup_accumulates_actions_and_recent_events(tmp_path):
    watchdog = load_watchdog()
    first = {
        "finished_at": "2026-06-29T07:40:00+00:00",
        "summary": {
            "status": "ok",
            "expired": 1,
            "stuck": 0,
            "requeued_expired": 1,
            "requeued_stuck": 0,
            "dead_lettered_expired": 0,
            "dead_lettered_stuck": 0,
        },
    }
    second = {
        "finished_at": "2026-06-29T07:45:00+00:00",
        "summary": {
            "status": "degraded",
            "expired": 0,
            "stuck": 2,
            "requeued_expired": 0,
            "requeued_stuck": 1,
            "dead_lettered_expired": 0,
            "dead_lettered_stuck": 1,
        },
    }

    watchdog.update_rollup(first, tmp_path)
    rollup = watchdog.update_rollup(second, tmp_path)

    assert rollup["runs_total"] == 2
    assert rollup["runs_ok"] == 1
    assert rollup["runs_degraded"] == 1
    assert rollup["actions_total"] == 6
    assert rollup["totals"]["expired"] == 1
    assert rollup["totals"]["stuck"] == 2
    assert rollup["totals"]["requeued_expired"] == 1
    assert rollup["totals"]["requeued_stuck"] == 1
    assert rollup["totals"]["dead_lettered_stuck"] == 1
    assert rollup["recent_actions"][0]["at"] == "2026-06-29T07:45:00+00:00"


def test_should_notify_only_on_action_or_problem():
    watchdog = load_watchdog()

    assert watchdog.should_notify({"status": "ok", "expired": 0, "stuck": 0, "requeued_stuck": 0}) is False
    assert watchdog.should_notify({"status": "degraded", "expired": 0, "stuck": 0}) is True
    assert watchdog.should_notify({"status": "ok", "expired": 1, "stuck": 0}) is True
    assert watchdog.should_notify({"status": "ok", "expired": 0, "dead_lettered_stuck": 1}) is True


def test_maybe_send_telegram_report_skips_clean_report(tmp_path, monkeypatch):
    watchdog = load_watchdog()
    report = {"summary": {"status": "ok", "expired": 0, "stuck": 0, "requeued_expired": 0, "requeued_stuck": 0}}
    md = tmp_path / "report.md"
    md.write_text("# clean\n", encoding="utf-8")
    sent = []
    monkeypatch.setattr(watchdog, "send_telegram_message", lambda *args, **kwargs: sent.append(args) or {})

    result = watchdog.maybe_send_telegram_report(
        report,
        md,
        token="token",
        chat_id=123,
        state_path=tmp_path / "missing.json",
        title="Watchdog",
        timeout=1,
    )

    assert result == {"status": "skipped", "reason": "no_action"}
    assert sent == []


def test_maybe_send_telegram_report_sends_action_report_and_sanitizes(tmp_path, monkeypatch):
    watchdog = load_watchdog()
    report = {"summary": {"status": "ok", "expired": 0, "stuck": 1, "requeued_expired": 0, "requeued_stuck": 1}}
    md = tmp_path / "report.md"
    md.write_text("token=SECRET\nnormal line\n", encoding="utf-8")
    messages = []

    def fake_send(token, chat_id, text, timeout=35):
        messages.append({"token": token, "chat_id": chat_id, "text": text, "timeout": timeout})
        return {}

    monkeypatch.setattr(watchdog, "send_telegram_message", fake_send)

    result = watchdog.maybe_send_telegram_report(
        report,
        md,
        token="telegram-token",
        chat_id=123,
        state_path=tmp_path / "missing.json",
        title="Watchdog",
        timeout=2,
    )

    assert result["status"] == "sent"
    assert result["chat_id"] == 123
    assert messages
    assert "SECRET" not in messages[0]["text"]
    assert "token=[REDACTED]" in messages[0]["text"]


def test_owner_chat_id_from_state_reads_owner_or_tracked(tmp_path):
    watchdog = load_watchdog()
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"owner_chat_id": 111, "tracked": {"x": {"chat_id": 222}}}), encoding="utf-8")
    assert watchdog.owner_chat_id_from_state(state) == 111

    state.write_text(json.dumps({"tracked": {"x": {"chat_id": 222}}}), encoding="utf-8")
    assert watchdog.owner_chat_id_from_state(state) == 222
