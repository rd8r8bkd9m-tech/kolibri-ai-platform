from __future__ import annotations

import os
from pathlib import Path
import shutil
import sqlite3
import time

import pytest

from app.database import initialize_database
from app import release_monitor


RELEASE_ID = "kolibri-v3-0123456789ab-abcdef012345"
RELEASE_COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _arguments(tmp_path: Path):
    database = tmp_path / "data" / "kolibri-v3.db"
    database.parent.mkdir(mode=0o700)
    initialize_database(database)
    backup_root = tmp_path / "backups"
    backup_directory = backup_root / "daily"
    backup_directory.mkdir(parents=True, mode=0o700)
    backup = backup_directory / "kolibri-v3.db"
    shutil.copyfile(database, backup)
    backup.chmod(0o600)
    systemctl = tmp_path / "systemctl"
    journalctl = tmp_path / "journalctl"
    for executable in (systemctl, journalctl):
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
    return release_monitor._build_parser().parse_args(
        [
            "--database",
            str(database),
            "--backup-root",
            str(backup_root),
            "--backup-owner-uid",
            str(os.getuid()),
            "--backend-url",
            "http://127.0.0.1:18002/v1/ready",
            "--frontend-url",
            "http://127.0.0.1:13103/api/health",
            "--public-url",
            "https://kolibriai.test/readyz",
            "--release-id",
            RELEASE_ID,
            "--release-commit",
            RELEASE_COMMIT,
            "--expected-schema",
            "44",
            "--backend-unit",
            "kolibri-v3-backend.service",
            "--frontend-unit",
            "kolibri-v3-frontend.service",
            "--product-worker-unit",
            "kolibri-v3-product-run-worker.service",
            "--backup-service-unit",
            "kolibri-v3-database-backup.service",
            "--systemctl",
            str(systemctl),
            "--journalctl",
            str(journalctl),
            "--minimum-free-bytes",
            str(64 * 1024**2),
        ]
    )


def _healthy_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        release_monitor,
        "_endpoint_ready",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        release_monitor,
        "_service_active",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        release_monitor,
        "_service_result_success",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        release_monitor,
        "_journal_metrics",
        lambda *args, **kwargs: {
            "requestCount": 100,
            "errorCount": 1,
            "errorRateBps": 100,
            "p95DurationMs": 240,
        },
    )
    monkeypatch.setattr(
        release_monitor,
        "_tls_metrics",
        lambda *args, **kwargs: (
            {"tlsRemainingSeconds": 30 * 24 * 60 * 60},
            [],
        ),
    )


def test_monitor_reports_only_bounded_aggregate_release_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments = _arguments(tmp_path)
    _healthy_dependencies(monkeypatch)

    result = release_monitor.run_monitor(arguments)

    assert result["status"] == "ok"
    assert result["alerts"] == []
    assert result["releaseId"] == RELEASE_ID
    assert result["releaseCommit"] == RELEASE_COMMIT
    assert result["metrics"]["schemaVersion"] == 44
    assert result["metrics"]["stuckRuns"] == 0
    assert result["metrics"]["errorRateBps"] == 100
    serialized = str(result)
    assert "127.0.0.1" not in serialized
    assert str(tmp_path) not in serialized


def test_monitor_raises_every_required_local_alert_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments = _arguments(tmp_path)
    endpoint_results = iter((False, False, False))
    monkeypatch.setattr(
        release_monitor,
        "_endpoint_ready",
        lambda *args, **kwargs: next(endpoint_results),
    )
    monkeypatch.setattr(
        release_monitor,
        "_service_active",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        release_monitor,
        "_service_result_success",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        release_monitor,
        "_journal_metrics",
        lambda *args, **kwargs: {
            "requestCount": 100,
            "errorCount": 6,
            "errorRateBps": 600,
            "p95DurationMs": 4_000,
        },
    )
    database = sqlite3.connect(arguments.database)
    try:
        old = "2000-01-01T00:00:00+00:00"
        database.execute(
            """
            INSERT INTO chat_runs (
                tenant_id, id, project_id, thread_id, client_run_id,
                request_hash, input_message_id, requested_by_user_id,
                selected_profile, status, heartbeat_at, created_at, updated_at
            ) VALUES (
                'tenant_monitor', 'run_monitor', 'project_monitor',
                'thread_monitor', 'client_monitor', ?,
                'message_monitor', 'user_monitor', 'codex-cli', 'running',
                ?, ?, ?
            )
            """,
            ("sha256:" + "0" * 64, old, old, old),
        )
        database.commit()
    finally:
        database.close()
    monkeypatch.setattr(
        release_monitor,
        "_tls_metrics",
        lambda *args, **kwargs: (
            {"tlsRemainingSeconds": 24 * 60 * 60},
            ["tls_expiring"],
        ),
    )
    backup = next(arguments.backup_root.rglob("kolibri-v3.db"))
    stale_time = int(time.time()) - arguments.max_backup_age_seconds - 1
    os.utime(backup, (stale_time, stale_time))
    real_disk_usage = shutil.disk_usage
    monkeypatch.setattr(
        release_monitor.shutil,
        "disk_usage",
        lambda path: shutil._ntuple_diskusage(1, 1, 0),
    )

    result = release_monitor.run_monitor(arguments)

    assert result["status"] == "alert"
    assert set(result["alerts"]) == {
        "backend_not_ready",
        "backend_stopped",
        "database_backup_stale",
        "database_backup_job_failed",
        "disk_space_low",
        "error_rate_spike",
        "frontend_not_ready",
        "frontend_stopped",
        "product_worker_stopped",
        "public_down",
        "stuck_runs",
        "tls_expiring",
    }
    monkeypatch.setattr(release_monitor.shutil, "disk_usage", real_disk_usage)


def test_monitor_fails_closed_when_metrics_or_backup_are_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments = _arguments(tmp_path)
    _healthy_dependencies(monkeypatch)
    monkeypatch.setattr(
        release_monitor,
        "_journal_metrics",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("sensitive journal detail")
        ),
    )
    next(arguments.backup_root.rglob("kolibri-v3.db")).unlink()

    result = release_monitor.run_monitor(arguments)

    assert result["status"] == "alert"
    assert result["alerts"] == [
        "database_backup_missing",
        "error_metrics_unavailable",
    ]
    assert "sensitive" not in str(result)


@pytest.mark.parametrize(
    ("option", "value", "code"),
    (
        (
            "backend_url",
            "http://external.example:18002/v1/ready",
            "monitor_loopback_url_required",
        ),
        ("public_url", "http://kolibriai.test/readyz", "monitor_url_invalid"),
        ("release_id", "release\nunsafe", "release_id_invalid"),
        ("backend_unit", "../../unsafe.service", "service_unit_invalid"),
    ),
)
def test_monitor_rejects_unsafe_configuration(
    tmp_path: Path,
    option: str,
    value: str,
    code: str,
) -> None:
    arguments = _arguments(tmp_path)
    setattr(arguments, option, value)

    with pytest.raises(release_monitor.MonitorConfigurationError, match=code):
        release_monitor.run_monitor(arguments)


def test_journal_metrics_are_bounded_and_ignore_non_contract_lines(
    tmp_path: Path,
) -> None:
    journalctl = tmp_path / "journalctl"
    journalctl.write_text(
        "\n".join(
            (
                "#!/bin/sh",
                "cat <<'EOF'",
                '{"event":"http_request_complete","status":200,"durationMs":10}',
                '{"event":"http_request_complete","status":503,"durationMs":30}',
                '{"event":"other","status":599,"durationMs":999999}',
                "token=must-not-be-parsed",
                "EOF",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    journalctl.chmod(0o755)

    metrics = release_monitor._journal_metrics(
        journalctl,
        backend_unit="kolibri-v3-backend.service",
        since_epoch=1,
    )

    assert metrics == {
        "requestCount": 2,
        "errorCount": 1,
        "errorRateBps": 5_000,
        "p95DurationMs": 30,
    }
