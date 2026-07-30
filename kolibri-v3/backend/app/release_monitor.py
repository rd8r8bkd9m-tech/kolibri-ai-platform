"""Fail-closed production observability check for one immutable V3 release.

The monitor deliberately emits aggregate counters and bounded alert codes only.
It never serializes URLs, paths, database rows, prompts, cookies, or credentials.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import ssl
import stat
import subprocess
import sys
import time
from typing import Any, NoReturn
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from cryptography import x509


_RELEASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RELEASE_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_UNIT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}[.]service$")
_BACKUP_NAME_PATTERN = re.compile(r"^kolibri-v3(?:-[A-Za-z0-9._-]{1,96})?[.]db$")
_MAX_HTTP_BODY_BYTES = 4_096
_MAX_JOURNAL_BYTES = 4 * 1024 * 1024
_MAX_JOURNAL_LINES = 10_000


class MonitorConfigurationError(RuntimeError):
    """The monitor was invoked with an unsafe or incomplete contract."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _fail_configuration(code: str) -> NoReturn:
    raise MonitorConfigurationError(code)


def _canonical_regular_file(path: Path, *, code: str) -> Path:
    if not path.is_absolute():
        _fail_configuration(f"{code}_not_absolute")
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        _fail_configuration(f"{code}_unavailable")
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or resolved != path
    ):
        _fail_configuration(f"{code}_unsafe")
    return resolved


def _canonical_directory(path: Path, *, code: str) -> Path:
    if not path.is_absolute():
        _fail_configuration(f"{code}_not_absolute")
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        _fail_configuration(f"{code}_unavailable")
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or resolved != path
        or metadata.st_mode & 0o022
    ):
        _fail_configuration(f"{code}_unsafe")
    return resolved


def _validated_url(
    raw_url: str,
    *,
    public: bool,
    expected_path: str,
) -> str:
    parsed = urlsplit(raw_url)
    try:
        parsed_port = parsed.port
    except ValueError:
        _fail_configuration("monitor_url_port_invalid")
    allowed_schemes = {"https"} if public else {"http"}
    if (
        parsed.scheme not in allowed_schemes
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != expected_path
    ):
        _fail_configuration("monitor_url_invalid")
    if not public and parsed.hostname not in {"127.0.0.1", "::1"}:
        _fail_configuration("monitor_loopback_url_required")
    if (
        (not public and parsed_port is None)
        or (
            parsed_port is not None
            and not 1_024 <= parsed_port <= 65_535
            and not (public and parsed_port == 443)
        )
    ):
        _fail_configuration("monitor_url_port_invalid")
    return raw_url


def _expected_payload(release_id: str, release_commit: str) -> dict[str, str]:
    return {
        "status": "ok",
        "service": "kolibri-v3",
        "releaseId": release_id,
        "releaseCommit": release_commit,
    }


def _endpoint_ready(
    url: str,
    *,
    release_id: str,
    release_commit: str,
) -> bool:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "kolibri-monitor/1"},
        method="GET",
    )
    try:
        with build_opener(_NoRedirect).open(request, timeout=5) as response:
            declared_length = response.headers.get("Content-Length")
            if (
                declared_length is not None
                and int(declared_length) > _MAX_HTTP_BODY_BYTES
            ):
                return False
            payload_bytes = response.read(_MAX_HTTP_BODY_BYTES + 1)
            if len(payload_bytes) > _MAX_HTTP_BODY_BYTES:
                return False
            payload = json.loads(payload_bytes.decode("utf-8"))
    except (
        HTTPError,
        URLError,
        OSError,
        TimeoutError,
        UnicodeDecodeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return False
    return payload == _expected_payload(release_id, release_commit)


def _service_active(systemctl: Path, unit: str) -> bool:
    try:
        result = subprocess.run(
            [str(systemctl), "is-active", "--quiet", unit],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _service_result_success(systemctl: Path, unit: str) -> bool:
    try:
        result = subprocess.run(
            [
                str(systemctl),
                "show",
                "--property=Result",
                "--value",
                unit,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return (
        result.returncode == 0
        and len(result.stdout) <= 64
        and result.stdout.strip() in {b"", b"success"}
    )


def _journal_metrics(
    journalctl: Path,
    *,
    backend_unit: str,
    since_epoch: int,
) -> dict[str, int]:
    try:
        result = subprocess.run(
            [
                str(journalctl),
                "--unit",
                backend_unit,
                "--since",
                f"@{since_epoch}",
                "--output=cat",
                "--no-pager",
                "--lines",
                str(_MAX_JOURNAL_LINES),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("journal_unavailable") from exc
    if result.returncode != 0 or len(result.stdout) > _MAX_JOURNAL_BYTES:
        raise RuntimeError("journal_unavailable")

    durations: list[float] = []
    error_count = 0
    for raw_line in result.stdout.splitlines():
        if not raw_line.startswith(b"{"):
            continue
        try:
            event = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(event, dict) or event.get("event") != "http_request_complete":
            continue
        status_code = event.get("status")
        duration_ms = event.get("durationMs")
        if (
            isinstance(status_code, bool)
            or not isinstance(status_code, int)
            or not 100 <= status_code <= 599
            or isinstance(duration_ms, bool)
            or not isinstance(duration_ms, (int, float))
            or not math.isfinite(float(duration_ms))
            or not 0 <= float(duration_ms) <= 86_400_000
        ):
            continue
        durations.append(float(duration_ms))
        if status_code >= 500:
            error_count += 1

    durations.sort()
    request_count = len(durations)
    p95_duration_ms = (
        int(round(durations[max(0, math.ceil(request_count * 0.95) - 1)]))
        if durations
        else 0
    )
    error_rate_bps = (
        (error_count * 10_000) // request_count if request_count else 0
    )
    return {
        "requestCount": request_count,
        "errorCount": error_count,
        "errorRateBps": error_rate_bps,
        "p95DurationMs": p95_duration_ms,
    }


def _database_metrics(
    database_path: Path,
    *,
    expected_schema: int,
    now_epoch: int,
    stuck_run_seconds: int,
) -> tuple[dict[str, int], list[str]]:
    alerts: list[str] = []
    try:
        database = sqlite3.connect(
            f"{database_path.as_uri()}?mode=ro",
            uri=True,
            timeout=5,
        )
        database.row_factory = sqlite3.Row
        try:
            database.execute("PRAGMA query_only = ON")
            if database.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("quick_check_failed")
            schema_version = int(
                database.execute("PRAGMA user_version").fetchone()[0]
            )
            running = database.execute(
                """
                SELECT
                    COUNT(*) AS running_count,
                    COALESCE(SUM(
                        CASE
                            WHEN unixepoch(heartbeat_at) IS NULL
                              OR unixepoch(heartbeat_at) < ?
                            THEN 1
                            ELSE 0
                        END
                    ), 0) AS stuck_count
                FROM chat_runs
                WHERE status = 'running'
                """,
                (now_epoch - stuck_run_seconds,),
            ).fetchone()
            product_queue = int(
                database.execute(
                    """
                    SELECT COUNT(*)
                    FROM product_run_outbox
                    WHERE state NOT IN ('blocked', 'completed')
                    """
                ).fetchone()[0]
            )
            direct_queue = int(
                database.execute(
                    """
                    SELECT COUNT(*)
                    FROM direct_run_outbox
                    WHERE state NOT IN ('blocked', 'completed')
                    """
                ).fetchone()[0]
            )
        finally:
            database.close()
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return {
            "schemaVersion": 0,
            "runningRuns": 0,
            "stuckRuns": 0,
            "productQueueDepth": 0,
            "directQueueDepth": 0,
        }, ["database_check_failed"]

    if schema_version != expected_schema:
        alerts.append("database_schema_mismatch")
    stuck_runs = int(running["stuck_count"])
    if stuck_runs:
        alerts.append("stuck_runs")
    return {
        "schemaVersion": schema_version,
        "runningRuns": int(running["running_count"]),
        "stuckRuns": stuck_runs,
        "productQueueDepth": product_queue,
        "directQueueDepth": direct_queue,
    }, alerts


def _latest_backup(
    backup_root: Path,
    *,
    expected_owner_uid: int,
) -> Path | None:
    latest: tuple[int, Path] | None = None
    for root, directory_names, file_names in os.walk(
        backup_root,
        topdown=True,
        followlinks=False,
    ):
        root_path = Path(root)
        safe_directories: list[str] = []
        for name in directory_names:
            candidate = root_path / name
            try:
                metadata = candidate.lstat()
            except OSError:
                continue
            if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
                safe_directories.append(name)
        directory_names[:] = safe_directories
        for name in file_names:
            if _BACKUP_NAME_PATTERN.fullmatch(name) is None:
                continue
            candidate = root_path / name
            try:
                metadata = candidate.lstat()
                resolved = candidate.resolve(strict=True)
            except OSError:
                continue
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or resolved != candidate
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != expected_owner_uid
            ):
                continue
            identity = (metadata.st_mtime_ns, candidate)
            if latest is None or identity[0] > latest[0]:
                latest = identity
    return latest[1] if latest is not None else None


def _backup_metrics(
    backup_root: Path,
    *,
    expected_owner_uid: int,
    expected_schema: int,
    now_epoch: int,
    max_backup_age_seconds: int,
) -> tuple[dict[str, int], list[str]]:
    backup = _latest_backup(
        backup_root,
        expected_owner_uid=expected_owner_uid,
    )
    if backup is None:
        return {"backupAgeSeconds": -1}, ["database_backup_missing"]
    try:
        age_seconds = max(0, now_epoch - int(backup.stat().st_mtime))
        database = sqlite3.connect(
            f"{backup.as_uri()}?mode=ro",
            uri=True,
            timeout=5,
        )
        try:
            quick_check = database.execute("PRAGMA quick_check").fetchone()[0]
            schema_version = int(
                database.execute("PRAGMA user_version").fetchone()[0]
            )
        finally:
            database.close()
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return {"backupAgeSeconds": -1}, ["database_backup_invalid"]
    alerts: list[str] = []
    if quick_check != "ok" or schema_version != expected_schema:
        alerts.append("database_backup_invalid")
    if age_seconds > max_backup_age_seconds:
        alerts.append("database_backup_stale")
    return {"backupAgeSeconds": age_seconds}, alerts


def _tls_metrics(
    public_url: str,
    *,
    now_epoch: int,
    warning_seconds: int,
) -> tuple[dict[str, int], list[str]]:
    parsed = urlsplit(public_url)
    hostname = parsed.hostname
    if hostname is None:
        return {"tlsRemainingSeconds": -1}, ["tls_certificate_invalid"]
    port = parsed.port or 443
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=5) as raw_socket:
            with context.wrap_socket(
                raw_socket,
                server_hostname=hostname,
            ) as tls_socket:
                certificate_bytes = tls_socket.getpeercert(binary_form=True)
        if not certificate_bytes:
            raise ValueError("peer certificate missing")
        certificate = x509.load_der_x509_certificate(certificate_bytes)
        remaining_seconds = int(
            certificate.not_valid_after_utc.timestamp()
        ) - now_epoch
    except (OSError, ssl.SSLError, ValueError):
        return {"tlsRemainingSeconds": -1}, ["tls_certificate_invalid"]
    alerts = (
        ["tls_expiring"]
        if remaining_seconds <= warning_seconds
        else []
    )
    return {"tlsRemainingSeconds": remaining_seconds}, alerts


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kolibri V3 immutable release monitor",
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--backup-owner-uid", type=int, default=0)
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--release-commit", required=True)
    parser.add_argument("--expected-schema", type=int, required=True)
    parser.add_argument("--backend-unit", required=True)
    parser.add_argument("--frontend-unit", required=True)
    parser.add_argument("--product-worker-unit", required=True)
    parser.add_argument("--backup-service-unit", required=True)
    parser.add_argument(
        "--systemctl",
        type=Path,
        default=Path("/usr/bin/systemctl"),
    )
    parser.add_argument(
        "--journalctl",
        type=Path,
        default=Path("/usr/bin/journalctl"),
    )
    parser.add_argument("--minimum-free-bytes", type=int, default=10 * 1024**3)
    parser.add_argument("--max-backup-age-seconds", type=int, default=36 * 60 * 60)
    parser.add_argument("--tls-warning-seconds", type=int, default=14 * 24 * 60 * 60)
    parser.add_argument("--stuck-run-seconds", type=int, default=5 * 60)
    parser.add_argument("--error-window-seconds", type=int, default=5 * 60)
    parser.add_argument("--error-rate-threshold-bps", type=int, default=500)
    parser.add_argument("--minimum-error-samples", type=int, default=20)
    return parser


def _validate_arguments(arguments: argparse.Namespace) -> None:
    if _RELEASE_ID_PATTERN.fullmatch(arguments.release_id) is None:
        _fail_configuration("release_id_invalid")
    if _RELEASE_COMMIT_PATTERN.fullmatch(arguments.release_commit) is None:
        _fail_configuration("release_commit_invalid")
    for unit in (
        arguments.backend_unit,
        arguments.frontend_unit,
        arguments.product_worker_unit,
        arguments.backup_service_unit,
    ):
        if _UNIT_PATTERN.fullmatch(unit) is None:
            _fail_configuration("service_unit_invalid")
    for value, minimum, maximum, code in (
        (arguments.expected_schema, 1, 999, "expected_schema_invalid"),
        (arguments.backup_owner_uid, 0, 2**31 - 1, "backup_owner_invalid"),
        (
            arguments.minimum_free_bytes,
            64 * 1024**2,
            2**63 - 1,
            "disk_threshold_invalid",
        ),
        (
            arguments.max_backup_age_seconds,
            3_600,
            7 * 24 * 60 * 60,
            "backup_age_invalid",
        ),
        (
            arguments.tls_warning_seconds,
            3_600,
            90 * 24 * 60 * 60,
            "tls_warning_invalid",
        ),
        (
            arguments.stuck_run_seconds,
            30,
            24 * 60 * 60,
            "stuck_run_invalid",
        ),
        (arguments.error_window_seconds, 60, 60 * 60, "error_window_invalid"),
        (arguments.error_rate_threshold_bps, 1, 10_000, "error_rate_invalid"),
        (arguments.minimum_error_samples, 1, 100_000, "error_samples_invalid"),
    ):
        if isinstance(value, bool) or not minimum <= value <= maximum:
            _fail_configuration(code)


def run_monitor(arguments: argparse.Namespace) -> dict[str, Any]:
    _validate_arguments(arguments)
    database_path = _canonical_regular_file(arguments.database, code="database")
    backup_root = _canonical_directory(arguments.backup_root, code="backup_root")
    systemctl = _canonical_regular_file(arguments.systemctl, code="systemctl")
    journalctl = _canonical_regular_file(arguments.journalctl, code="journalctl")
    backend_url = _validated_url(
        arguments.backend_url,
        public=False,
        expected_path="/v1/ready",
    )
    frontend_url = _validated_url(
        arguments.frontend_url,
        public=False,
        expected_path="/api/health",
    )
    public_url = _validated_url(
        arguments.public_url,
        public=True,
        expected_path="/readyz",
    )

    now_epoch = int(time.time())
    alerts: list[str] = []
    if not _endpoint_ready(
        backend_url,
        release_id=arguments.release_id,
        release_commit=arguments.release_commit,
    ):
        alerts.append("backend_not_ready")
    if not _endpoint_ready(
        frontend_url,
        release_id=arguments.release_id,
        release_commit=arguments.release_commit,
    ):
        alerts.append("frontend_not_ready")
    if not _endpoint_ready(
        public_url,
        release_id=arguments.release_id,
        release_commit=arguments.release_commit,
    ):
        alerts.append("public_down")

    for unit, code in (
        (arguments.backend_unit, "backend_stopped"),
        (arguments.frontend_unit, "frontend_stopped"),
        (arguments.product_worker_unit, "product_worker_stopped"),
    ):
        if not _service_active(systemctl, unit):
            alerts.append(code)
    if not _service_result_success(systemctl, arguments.backup_service_unit):
        alerts.append("database_backup_job_failed")

    database_metrics, database_alerts = _database_metrics(
        database_path,
        expected_schema=arguments.expected_schema,
        now_epoch=now_epoch,
        stuck_run_seconds=arguments.stuck_run_seconds,
    )
    alerts.extend(database_alerts)

    available_bytes = shutil.disk_usage(database_path.parent).free
    if available_bytes < arguments.minimum_free_bytes:
        alerts.append("disk_space_low")

    backup_metrics, backup_alerts = _backup_metrics(
        backup_root,
        expected_owner_uid=arguments.backup_owner_uid,
        expected_schema=arguments.expected_schema,
        now_epoch=now_epoch,
        max_backup_age_seconds=arguments.max_backup_age_seconds,
    )
    alerts.extend(backup_alerts)

    tls_metrics, tls_alerts = _tls_metrics(
        public_url,
        now_epoch=now_epoch,
        warning_seconds=arguments.tls_warning_seconds,
    )
    alerts.extend(tls_alerts)

    try:
        journal_metrics = _journal_metrics(
            journalctl,
            backend_unit=arguments.backend_unit,
            since_epoch=now_epoch - arguments.error_window_seconds,
        )
    except RuntimeError:
        journal_metrics = {
            "requestCount": 0,
            "errorCount": 0,
            "errorRateBps": 0,
            "p95DurationMs": 0,
        }
        alerts.append("error_metrics_unavailable")
    if (
        journal_metrics["requestCount"] >= arguments.minimum_error_samples
        and journal_metrics["errorRateBps"]
        > arguments.error_rate_threshold_bps
    ):
        alerts.append("error_rate_spike")

    metrics = {
        **database_metrics,
        **backup_metrics,
        **tls_metrics,
        **journal_metrics,
        "diskAvailableBytes": available_bytes,
    }
    unique_alerts = sorted(set(alerts))
    return {
        "event": "release_monitor_result",
        "status": "alert" if unique_alerts else "ok",
        "releaseId": arguments.release_id,
        "releaseCommit": arguments.release_commit,
        "checkedAt": now_epoch,
        "alerts": unique_alerts,
        "metrics": metrics,
    }


def main() -> None:
    try:
        result = run_monitor(_build_parser().parse_args())
    except MonitorConfigurationError as error:
        print(
            json.dumps(
                {
                    "event": "release_monitor_result",
                    "status": "configuration_error",
                    "code": str(error),
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(3) from None
    except Exception:
        print(
            '{"code":"monitor_internal_error","event":"release_monitor_result",'
            '"status":"configuration_error"}',
            file=sys.stderr,
        )
        raise SystemExit(3) from None
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    if result["status"] != "ok":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
