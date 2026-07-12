import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_home_watchdog_unit_is_recovery_only_and_cannot_send_telegram() -> None:
    unit = (ROOT / "ops/systemd/kolibri-factory-lease-watchdog.service").read_text(
        encoding="utf-8"
    )

    assert "--telegram-on-action" not in unit
    assert "KOLIBRI_FACTORY_WATCHDOG_STALE_AFTER=30" in unit
    assert "ExecStart=/usr/bin/python3 -B" in unit
    assert "Environment=PYTHONDONTWRITEBYTECODE=1" in unit


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
        if path == "/v1/tasks/failures?error_type=deliverable_gate_failed&limit=50":
            return {"error_type": "deliverable_gate_failed", "total": 0, "tasks": []}
        raise AssertionError(path)

    monkeypatch.setattr(watchdog, "call_control", fake_call)

    report = watchdog.run_watchdog("http://control:9101", limit=50, stale_after_seconds=3600, timeout=7)

    assert [call[1] for call in calls] == [
        "/v1/health",
        "/v1/tasks/reap-expired",
        "/v1/tasks/sweep-stuck",
        "/v1/tasks/failures?error_type=deliverable_gate_failed&limit=50",
    ]
    assert calls[1][2] == {"limit": 50}
    assert calls[2][2] == {"limit": 50, "stale_after_seconds": 3600}
    assert report["summary"]["status"] == "ok"
    assert report["summary"]["lease_index_total"] == 1
    assert report["summary"]["stuck"] == 0
    assert report["summary"]["deliverable_gate_failed"] == 0


def test_build_summary_accepts_canonical_home_health_envelope():
    watchdog = load_watchdog()

    summary = watchdog.build_summary(
        {
            "status": "completed",
            "node": "home",
            "data": {"redis": "PONG", "queue_backend": "redis"},
        },
        None,
        {"task_total": 12, "lease_index_total": 0, "expired": 0, "requeued_total": 0, "dead_lettered_total": 0},
        {"task_total": 12, "lease_index_total": 0, "stuck": 0, "requeued_total": 0, "dead_lettered_total": 0, "stale_after_seconds": 3600},
        {"total": 0, "tasks": []},
    )

    assert summary["status"] == "ok"
    assert summary["redis"] == "PONG"
    assert summary["queue_backend"] == "redis"


def test_failure_markdown_says_not_collected_instead_of_none():
    watchdog = load_watchdog()
    report = {
        "control_url": "http://10.99.0.1:9101",
        "started_at": "2026-07-10T13:31:03+00:00",
        "finished_at": "2026-07-10T13:31:03+00:00",
        "summary": {"status": "failed", "error": "HTTP Error 404: Not Found"},
        "error": "HTTP Error 404: Not Found",
    }

    markdown = watchdog.markdown_report(report)

    assert "HTTP Error 404: Not Found" in markdown
    assert "не собрано" in markdown
    assert "`None`" not in markdown


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
        if path == "/v1/tasks/failures?error_type=deliverable_gate_failed&limit=20":
            return {"error_type": "deliverable_gate_failed", "total": 0, "tasks": []}
        raise AssertionError(path)

    monkeypatch.setattr(watchdog, "call_control", fake_call)

    report = watchdog.run_watchdog("http://control:9101", limit=20, stale_after_seconds=3600, timeout=5, rebuild_indexes=True)

    assert calls == [
        "/v1/health",
        "/v1/tasks/rebuild-indexes",
        "/v1/tasks/reap-expired",
        "/v1/tasks/sweep-stuck",
        "/v1/tasks/failures?error_type=deliverable_gate_failed&limit=20",
    ]
    assert report["summary"]["rebuild_indexed"] == 690


def test_run_watchdog_reports_deliverable_gate_failures(tmp_path, monkeypatch):
    watchdog = load_watchdog()

    def fake_call(control_url, method, path, body=None, timeout=20):
        if path == "/v1/health":
            return {"status": "ok", "redis": "PONG", "queue_backend": "redis"}
        if path == "/v1/tasks/reap-expired":
            return {"task_total": 10, "lease_index_total": 0, "expired": 0, "requeued_total": 0, "dead_lettered_total": 0}
        if path == "/v1/tasks/sweep-stuck":
            return {"task_total": 10, "lease_index_total": 0, "stuck": 0, "requeued_total": 0, "dead_lettered_total": 0, "stale_after_seconds": 3600}
        if path == "/v1/tasks/failures?error_type=deliverable_gate_failed&limit=5":
            return {
                "error_type": "deliverable_gate_failed",
                "total": 1,
                "tasks": [{"task_id": "KOL-GATE-1", "error": "missing_checks"}],
            }
        raise AssertionError(path)

    monkeypatch.setattr(watchdog, "call_control", fake_call)

    report = watchdog.run_watchdog("http://control:9101", limit=5, stale_after_seconds=3600, timeout=7)

    assert report["summary"]["deliverable_gate_status"] == "ok"
    assert report["summary"]["deliverable_gate_failed"] == 1
    assert report["summary"]["deliverable_gate_recent"][0]["task_id"] == "KOL-GATE-1"
    watchdog.update_rollup(report, tmp_path)
    assert watchdog.should_notify(report["summary"]) is True


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
            "deliverable_gate_failed": 0,
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
            "deliverable_gate_failed": 1,
            "deliverable_gate_recent": [{"task_id": "KOL-GATE-1"}],
        },
    }

    watchdog.update_rollup(first, tmp_path)
    rollup = watchdog.update_rollup(second, tmp_path)

    assert rollup["runs_total"] == 2
    assert rollup["runs_ok"] == 1
    assert rollup["runs_degraded"] == 1
    assert rollup["actions_total"] == 7
    assert rollup["totals"]["expired"] == 1
    assert rollup["totals"]["stuck"] == 2
    assert rollup["totals"]["requeued_expired"] == 1
    assert rollup["totals"]["requeued_stuck"] == 1
    assert rollup["totals"]["dead_lettered_stuck"] == 1
    assert rollup["totals"]["deliverable_gate_failed"] == 1
    assert rollup["deliverable_gate_seen_task_ids"] == ["KOL-GATE-1"]
    assert rollup["recent_actions"][0]["at"] == "2026-06-29T07:45:00+00:00"


def test_should_notify_only_on_action_or_problem():
    watchdog = load_watchdog()

    assert watchdog.should_notify({"status": "ok", "expired": 0, "stuck": 0, "requeued_stuck": 0}) is False
    assert watchdog.should_notify({"status": "degraded", "expired": 0, "stuck": 0}) is True
    assert watchdog.should_notify({"status": "ok", "expired": 1, "stuck": 0}) is True
    assert watchdog.should_notify({"status": "ok", "expired": 0, "dead_lettered_stuck": 1}) is True
    assert watchdog.should_notify({"status": "ok", "expired": 0, "stuck": 0, "deliverable_gate_new": 1}) is True
    assert watchdog.should_notify({"status": "ok", "expired": 0, "stuck": 0, "deliverable_retry_failed": 1}) is True


def test_build_deliverable_retry_envelope_requires_evidence_contract(monkeypatch):
    watchdog = load_watchdog()
    monkeypatch.setattr(watchdog, "utc_now", lambda: "2026-06-29T08:20:00+00:00")

    envelope = watchdog.build_deliverable_retry_envelope(
        {
            "task_id": "KOL-GATE-1",
            "kind": "generic_implementation",
            "error": "deliverable_gate_failed:missing_checks",
            "envelope": {
                "objective": "Исправить Telegram формат",
                "target_node": "__no_such_node__",
                "acceptance": ["Use HTML parse_mode."],
            },
        }
    )

    assert envelope["task_id"] == "KOL-GATE-1-DELIVERABLE-RETRY"
    assert envelope["idempotency_key"] == "deliverable-retry:KOL-GATE-1"
    assert envelope["source_task_id"] == "KOL-GATE-1"
    assert envelope["retry_reason"] == "deliverable_gate_failed"
    assert envelope["source"]["kind"] == "watchdog_deliverable_retry"
    assert "target_node" not in envelope
    assert "Retry source task: KOL-GATE-1" in envelope["objective"]
    assert any("changed_files" in item for item in envelope["acceptance"])
    assert any("checks" in item for item in envelope["acceptance"])
    assert any("Commit and push" in item for item in envelope["acceptance"])


def test_create_deliverable_retry_tasks_uses_new_gate_ids(monkeypatch):
    watchdog = load_watchdog()
    calls = []

    def fake_call(control_url, method, path, body=None, timeout=20):
        calls.append((method, path, body, timeout))
        if method == "GET" and path == "/v1/tasks/KOL-GATE-1":
            return {
                "task_id": "KOL-GATE-1",
                "kind": "generic_implementation",
                "envelope": {"objective": "Fix deliverables", "target_node": "__no_such_node__"},
            }
        if method == "POST" and path == "/v1/tasks":
            assert body["task_id"] == "KOL-GATE-1-DELIVERABLE-RETRY"
            assert body["idempotency_key"] == "deliverable-retry:KOL-GATE-1"
            assert "target_node" not in body
            return {"task_id": body["task_id"], "state": "queued", "idempotency_key": body["idempotency_key"]}
        raise AssertionError(path)

    monkeypatch.setattr(watchdog, "call_control", fake_call)
    report = {"summary": {"deliverable_gate_new_task_ids": ["KOL-GATE-1"]}}

    retries = watchdog.create_deliverable_retry_tasks(report, "http://control:9101", timeout=3)

    assert retries["created"] == [
        {
            "source_task_id": "KOL-GATE-1",
            "task_id": "KOL-GATE-1-DELIVERABLE-RETRY",
            "state": "queued",
            "idempotency_key": "deliverable-retry:KOL-GATE-1",
        }
    ]
    assert retries["failed"] == []
    assert report["summary"]["deliverable_retry_created"] == 1
    assert report["summary"]["deliverable_retry_failed"] == 0
    assert [call[0:2] for call in calls] == [("GET", "/v1/tasks/KOL-GATE-1"), ("POST", "/v1/tasks")]


def test_readable_watchdog_report_removes_json_and_send_message_uses_html(monkeypatch):
    watchdog = load_watchdog()
    captured = {}

    def fake_urlopen(request, timeout=35):
        captured["data"] = request.data.decode("utf-8")

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return b'{"ok":true,"result":{"message_id":1}}'

        return Response()

    monkeypatch.setattr(watchdog.urllib.request, "urlopen", fake_urlopen)
    readable = watchdog.readable_report_text("# R\n\n```json\n{\"raw\":true}\n```\n\n2 < 3 & ok")
    result = watchdog.send_telegram_message("token", 100, readable)

    assert result == {"message_id": 1}
    payload = watchdog.urllib.parse.parse_qs(captured["data"])
    assert payload["parse_mode"] == ["HTML"]
    assert "{\"raw\"" not in payload["text"][0]
    assert "&lt;" in payload["text"][0]
    assert "&amp;" in payload["text"][0]


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


def test_maybe_send_telegram_report_suppresses_same_active_incident(tmp_path, monkeypatch):
    watchdog = load_watchdog()
    report = {"summary": {"status": "failed", "error": "HTTP Error 404: Not Found"}}
    md = tmp_path / "report.md"
    md.write_text("failed\n", encoding="utf-8")
    messages = []
    monkeypatch.setattr(
        watchdog,
        "send_telegram_message",
        lambda *args, **kwargs: messages.append(args) or {},
    )

    first = watchdog.maybe_send_telegram_report(
        report,
        md,
        token="token",
        chat_id=123,
        state_path=tmp_path / "gateway-state.json",
        title="Watchdog",
        timeout=1,
    )
    second = watchdog.maybe_send_telegram_report(
        report,
        md,
        token="token",
        chat_id=123,
        state_path=tmp_path / "gateway-state.json",
        title="Watchdog",
        timeout=1,
    )

    assert first["status"] == "sent"
    assert second == {"status": "skipped", "reason": "duplicate_incident"}
    assert len(messages) == 1


def test_owner_chat_id_from_state_reads_owner_or_tracked(tmp_path):
    watchdog = load_watchdog()
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"owner_chat_id": 111, "tracked": {"x": {"chat_id": 222}}}), encoding="utf-8")
    assert watchdog.owner_chat_id_from_state(state) == 111

    state.write_text(json.dumps({"tracked": {"x": {"chat_id": 222}}}), encoding="utf-8")
    assert watchdog.owner_chat_id_from_state(state) == 222
