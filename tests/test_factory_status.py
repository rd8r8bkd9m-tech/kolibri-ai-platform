from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from factory_status import build_factory_status, load_watchdog_status, merge_tasks_by_id, summarize_factory_failures


def test_build_factory_status_normalizes_control_plane_nodes():
    payload = {
        "summary": {
            "registered_nodes": 35,
            "canonical_nodes": 21,
            "fresh_nodes": 6,
            "fresh_non_draining_nodes": 3,
            "fresh_canonical_nodes": 3,
            "fresh_canonical_generic_implementation_nodes": 1,
            "mesh_shadow_duplicates": 13,
        },
        "nodes": [
            {
                "node_id": "primary-candidate",
                "hostname": "kolibri",
                "health": "online",
                "agent_id": "agent-host-primary",
                "pid": 120138,
                "capabilities": ["primary", "implementation", "review"],
                "cpu": 8,
                "ram": {"MemTotal": "12247028 kB", "MemAvailable": "11510364 kB"},
                "disk": {"free": 94581936128, "total": 105590231040},
            },
            {"node_id": "new", "health": "offline", "draining": True, "capabilities": ["review"], "ram": {}, "disk": {}},
        ]
    }
    watchdog = {
        "available": True,
        "rollup": {"runs_total": 4, "actions_total": 1, "totals": {"stuck": 1}},
        "latest_summary": {"status": "ok", "stuck": 0},
        "telegram": {"status": "skipped", "reason": "no_action"},
    }
    result = build_factory_status(
        payload,
        {
            "tasks": [
                {"state": "queued"},
                {"state": "running"},
                {
                    "task_id": "KOL-GATE-1",
                    "kind": "generic_implementation",
                    "state": "failed",
                    "error_type": "deliverable_gate_failed",
                    "error": "deliverable_gate_failed:missing_code_delta",
                    "updated_at": "2026-06-29T08:10:48+00:00",
                    "result_reference": "/tmp/result.json",
                },
            ]
        },
        {"status": "ok", "queue_backend": "redis"},
        watchdog,
    )

    assert result["status"] == "online"
    assert result["total_nodes"] == 35
    assert result["online_nodes"] == 6
    assert result["canonical_nodes"] == 21
    assert result["fresh_non_draining_nodes"] == 3
    assert result["ready_generic_implementation_nodes"] == 1
    assert result["stale_nodes"] == 29
    assert result["draining_nodes"] == 1
    assert result["mesh_shadow_duplicates"] == 13
    assert result["duplicate_nodes"] == 14
    assert result["node_summary"]["mesh_shadow_duplicates"] == 13
    assert result["queue_size"] == 2
    assert result["nodes"]["primary-candidate"]["role"] == "Директор"
    assert result["nodes"]["primary-candidate"]["ram_total_gb"] > 0
    assert result["control_plane"]["status"] == "ok"
    assert result["watchdog"]["rollup"]["runs_total"] == 4
    assert result["watchdog"]["rollup"]["totals"]["stuck"] == 1
    assert result["factory_failures"]["deliverable_gate_failed"] == 1
    assert result["factory_failures"]["needs_attention"] is True
    assert result["factory_failures"]["deliverable_gate_recent"][0]["task_id"] == "KOL-GATE-1"


def test_summarize_factory_failures_tracks_deliverable_gate_recent():
    summary = summarize_factory_failures(
        [
            {
                "task_id": "OLDER",
                "kind": "generic_implementation",
                "state": "failed",
                "error_type": "deliverable_gate_failed",
                "updated_at": "2026-06-29T08:00:00+00:00",
            },
            {
                "task_id": "NEWER",
                "kind": "owner_remote_task",
                "state": "failed",
                "error_type": "deliverable_gate_failed",
                "updated_at": "2026-06-29T08:10:00+00:00",
                "result": {"result_path": "/tmp/newer.json"},
            },
            {"task_id": "OTHER", "state": "dead_letter", "error_type": "runtime_error"},
        ]
    )

    assert summary["failed_total"] == 3
    assert summary["deliverable_gate_failed"] == 2
    assert summary["error_types"]["runtime_error"] == 1
    assert summary["needs_attention"] is True
    assert [item["task_id"] for item in summary["deliverable_gate_recent"]] == ["NEWER", "OLDER"]
    assert summary["deliverable_gate_recent"][0]["result_reference"] == "/tmp/newer.json"


def test_merge_tasks_by_id_keeps_failed_state_sample_visible():
    merged = merge_tasks_by_id(
        [{"task_id": "ACTIVE", "state": "running"}, {"task_id": "FAILED", "state": "running"}],
        [{"task_id": "FAILED", "state": "failed", "error_type": "deliverable_gate_failed"}],
    )

    by_id = {task["task_id"]: task for task in merged}
    assert by_id["ACTIVE"]["state"] == "running"
    assert by_id["FAILED"]["state"] == "failed"
    assert by_id["FAILED"]["error_type"] == "deliverable_gate_failed"


def test_load_watchdog_status_reads_rollup_and_latest(tmp_path):
    (tmp_path / "summary.json").write_text(
        '{"runs_total": 3, "runs_ok": 2, "runs_degraded": 1, "actions_total": 5, "totals": {"expired": 2}, "recent_actions": [{"at": "now"}], "updated_at": "2026-06-29T07:50:00+00:00"}',
        encoding="utf-8",
    )
    (tmp_path / "latest.json").write_text(
        '{"summary": {"status": "ok", "task_total": 693}, "telegram": {"status": "skipped", "reason": "no_action"}, "report_paths": {"markdown": "/tmp/latest.md"}}',
        encoding="utf-8",
    )

    status = load_watchdog_status(tmp_path)

    assert status["available"] is True
    assert status["rollup"]["runs_total"] == 3
    assert status["rollup"]["runs_degraded"] == 1
    assert status["rollup"]["actions_total"] == 5
    assert status["rollup"]["totals"]["expired"] == 2
    assert status["latest_summary"]["task_total"] == 693
    assert status["telegram"]["reason"] == "no_action"


def test_load_watchdog_status_is_safe_when_files_are_missing(tmp_path):
    status = load_watchdog_status(tmp_path)

    assert status["available"] is False
    assert status["rollup"]["runs_total"] == 0
    assert status["latest_summary"] == {}


def test_frontend_uses_live_factory_status_endpoint():
    app_source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.jsx").read_text(encoding="utf-8")

    assert "/api/factory/status" in app_source
    assert "/cluster/status" not in app_source
    assert "на базе 5 серверов" not in app_source
    assert "Фабрика Колибри" in app_source


def test_frontend_surfaces_control_plane_node_summary():
    cluster_panel_source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "components" / "control" / "ClusterPanel.jsx").read_text(encoding="utf-8")
    helper_source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "factoryStatus.js").read_text(encoding="utf-8")

    assert "getNodeSummary(status)" in cluster_panel_source
    assert "registered_nodes" in helper_source
    assert "canonical_nodes" in helper_source
    assert "fresh_non_draining_nodes" in helper_source
    assert "fresh_canonical_generic_implementation_nodes" in helper_source
    assert "mesh shadow duplicates" in cluster_panel_source
    assert "getWatchdogSummary(status)" in cluster_panel_source
    assert "Автолечение leases" in cluster_panel_source
    assert "runs_total" in helper_source
    assert "actions_total" in helper_source
    assert "getFactoryFailureSummary(status)" in cluster_panel_source
    assert "Контроль deliverables" in cluster_panel_source
    assert "deliverable_gate_failed" in helper_source
