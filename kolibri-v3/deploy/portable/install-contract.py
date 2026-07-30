#!/usr/bin/env python3
"""Fail-closed host preparation helpers for portable Kolibri V3 releases."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import NoReturn
from urllib.parse import urlsplit


INSTANCE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,47}$")
ACCOUNT_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
UNIT_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.@-]{0,127}[.]service$")
RELEASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
RELEASE_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
PLACEHOLDER_PATTERN = re.compile(r"@[A-Z_]+@")
WORKER_TEMPLATES = {
    "kolibri-v3-product-run-worker.service.in": "product-run-worker",
    "kolibri-v3-provider-enrollment-worker.service.in": (
        "provider-enrollment-worker"
    ),
    "kolibri-v3-estimate-reconciliation-audit.service.in": (
        "estimate-reconciliation-audit"
    ),
}
ENVIRONMENT_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
PRODUCT_WORKER_KEYS = (
    "KOLIBRI_V3_HOME_PRODUCT_COMMAND_URL",
    "KOLIBRI_V3_HOME_PRODUCT_GOAL_COMMAND_URL",
    "KOLIBRI_V3_HOME_PRODUCT_PROVIDER_COMMAND_URL",
)
PROVIDER_WORKER_KEYS = (
    "KOLIBRI_V3_PROVIDER_AUTHORITY_COMMAND_URL",
)
WORKER_CREDENTIALS = {
    "product": (
        "home-product-command-token",
        "home-product-identity-hmac-key",
    ),
    "provider": (
        "provider-authority-command-token",
        "provider-authority-identity-hmac-key",
    ),
}
class InstallContractError(RuntimeError):
    """A public-safe host preparation error."""


def fail(code: str) -> NoReturn:
    print(f"install_error={code}", file=sys.stderr)
    raise SystemExit(3)


def absolute_canonical_directory(raw_path: str, label: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        raise InstallContractError(f"{label}_not_absolute")
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise InstallContractError(f"{label}_unavailable") from exc
    if (
        path.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or resolved != path
    ):
        raise InstallContractError(f"{label}_unsafe")
    return path


def atomic_write(path: Path, payload: str, mode: int) -> None:
    if path.exists() or path.is_symlink():
        raise InstallContractError(f"render_target_exists path={path.name}")
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temporary:
        temporary.write(payload)
        temporary_path = Path(temporary.name)
    try:
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def validate_rendered_worker(
    name: str,
    payload: str,
    *,
    install_root: str,
    config_root: str,
    backend_service: str,
) -> None:
    if PLACEHOLDER_PATTERN.search(payload):
        raise InstallContractError(f"worker_placeholder_unresolved unit={name}")
    required = (
        "UMask=0077",
        f"EnvironmentFile={config_root}/backend.env",
        f"EnvironmentFile={config_root}/release.env",
        (
            "Environment=KOLIBRI_WORKER_EXPECTED_DATABASE_URL="
            f"sqlite:///{install_root}/var/kolibri-v3.db"
        ),
        f"{install_root}/libexec/worker_launcher.py",
        "ExecStartPre=",
        " --check",
    )
    for marker in required:
        if marker not in payload:
            raise InstallContractError(
                f"worker_template_contract_missing unit={name}"
            )
    if payload.index(
        f"EnvironmentFile={config_root}/backend.env"
    ) > payload.index(f"EnvironmentFile={config_root}/release.env"):
        raise InstallContractError(
            f"worker_environment_precedence_invalid unit={name}"
        )
    if name.endswith("estimate-reconciliation-audit.service"):
        if (
            "Type=oneshot" not in payload
            or "PrivateNetwork=true" not in payload
            or "--apply" in payload
            or "[Install]" in payload
        ):
            raise InstallContractError("audit_worker_not_fail_closed")
        return
    if (
        f"WantedBy={backend_service}" not in payload
        or "RestartPreventExitStatus=73 75 78" not in payload
        or "LoadCredential=" not in payload
        or "--materialize-credentials" not in payload
        or "%d/" in payload
    ):
        raise InstallContractError(
            f"durable_worker_not_fail_closed unit={name}"
        )


def render_workers(arguments: argparse.Namespace) -> None:
    if not INSTANCE_PATTERN.fullmatch(arguments.instance):
        raise InstallContractError("worker_instance_invalid")
    if not ACCOUNT_PATTERN.fullmatch(arguments.service_user):
        raise InstallContractError("worker_service_user_invalid")
    if not ACCOUNT_PATTERN.fullmatch(arguments.service_group):
        raise InstallContractError("worker_service_group_invalid")
    if not UNIT_PATTERN.fullmatch(arguments.backend_service):
        raise InstallContractError("worker_backend_service_invalid")

    source_root = absolute_canonical_directory(
        arguments.source_root,
        "worker_source_root",
    )
    output_root = absolute_canonical_directory(
        arguments.output_dir,
        "worker_output_root",
    )
    install_root = arguments.install_root.rstrip("/")
    config_root = arguments.config_root.rstrip("/")
    for value, label in (
        (install_root, "install_root"),
        (config_root, "config_root"),
    ):
        if (
            not value.startswith("/")
            or value == "/"
            or ".." in Path(value).parts
            or any(character in value for character in "\r\n\0")
        ):
            raise InstallContractError(f"worker_{label}_invalid")

    replacements = {
        "@INSTALL_ROOT@": install_root,
        "@CONFIG_ROOT@": config_root,
        "@SERVICE_USER@": arguments.service_user,
        "@SERVICE_GROUP@": arguments.service_group,
        "@BACKEND_SERVICE@": arguments.backend_service,
        "@INSTANCE@": arguments.instance,
    }
    for template_name, unit_role in WORKER_TEMPLATES.items():
        template_path = source_root / template_name
        try:
            template_metadata = template_path.lstat()
            payload = template_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise InstallContractError(
                f"worker_template_unreadable name={template_name}"
            ) from exc
        if template_path.is_symlink() or not stat.S_ISREG(
            template_metadata.st_mode
        ):
            raise InstallContractError(
                f"worker_template_unsafe name={template_name}"
            )
        for placeholder, value in replacements.items():
            payload = payload.replace(placeholder, value)
        unit_name = f"{arguments.instance}-{unit_role}.service"
        validate_rendered_worker(
            unit_name,
            payload,
            install_root=install_root,
            config_root=config_root,
            backend_service=arguments.backend_service,
        )
        target = output_root / unit_name
        atomic_write(target, payload, 0o644)
        print(f"worker_unit={target}")
    print("worker_render=ok")


def safe_absolute_unit_path(raw_value: str, label: str) -> str:
    value = raw_value.rstrip("/")
    path = Path(value)
    if (
        not value.startswith("/")
        or value == "/"
        or ".." in path.parts
        or any(character.isspace() or character == "\0" for character in value)
    ):
        raise InstallContractError(f"operation_{label}_invalid")
    return value


def safe_public_origin(raw_value: str) -> str:
    if (
        not raw_value
        or len(raw_value) > 2_048
        or any(
            character.isspace() or character == "\0"
            for character in raw_value
        )
    ):
        raise InstallContractError("operation_public_origin_invalid")
    try:
        parsed = urlsplit(raw_value)
        port = parsed.port
    except ValueError as exc:
        raise InstallContractError("operation_public_origin_invalid") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (port is not None and not 1 <= port <= 65535)
        or raw_value.rstrip("/") != raw_value
    ):
        raise InstallContractError("operation_public_origin_invalid")
    canonical = f"https://{parsed.hostname}"
    if port is not None:
        canonical = f"{canonical}:{port}"
    if raw_value != canonical:
        raise InstallContractError("operation_public_origin_invalid")
    return raw_value


def validate_operation_unit(name: str, payload: str) -> None:
    if PLACEHOLDER_PATTERN.search(payload):
        raise InstallContractError(
            f"operation_placeholder_unresolved unit={name}"
        )
    if "\0" in payload or "\r" in payload:
        raise InstallContractError(f"operation_unit_invalid unit={name}")
    if name.endswith("release-monitor.service"):
        required = (
            "Type=oneshot",
            "-m app.release_monitor",
            "--public-url ",
            "CapabilityBoundingSet=",
            "ReadOnlyPaths=",
        )
    elif name.endswith("release-monitor.timer"):
        required = (
            "OnUnitActiveSec=60s",
            "Persistent=true",
            "Unit=",
        )
    elif name.endswith("database-backup.service"):
        required = (
            "Type=oneshot",
            " scheduled-backup ",
            "OnFailure=",
            "PrivateNetwork=true",
            "ReadWritePaths=",
        )
    else:
        required = (
            "OnCalendar=*-*-* 02:15:00 UTC",
            "Persistent=true",
            "Unit=",
        )
    for marker in required:
        if marker not in payload:
            raise InstallContractError(
                f"operation_unit_contract_missing unit={name}"
            )


def render_operations(arguments: argparse.Namespace) -> None:
    if not INSTANCE_PATTERN.fullmatch(arguments.instance):
        raise InstallContractError("operation_instance_invalid")
    if not 1 <= arguments.backend_port <= 65535:
        raise InstallContractError("operation_backend_port_invalid")
    if not 1 <= arguments.frontend_port <= 65535:
        raise InstallContractError("operation_frontend_port_invalid")
    if not 1 <= arguments.expected_schema <= 9999:
        raise InstallContractError("operation_expected_schema_invalid")
    if not RELEASE_ID_PATTERN.fullmatch(arguments.release_id):
        raise InstallContractError("operation_release_id_invalid")
    if not RELEASE_COMMIT_PATTERN.fullmatch(arguments.release_commit):
        raise InstallContractError("operation_release_commit_invalid")
    if not ACCOUNT_PATTERN.fullmatch(arguments.service_user):
        raise InstallContractError("operation_service_user_invalid")
    if not ACCOUNT_PATTERN.fullmatch(arguments.service_group):
        raise InstallContractError("operation_service_group_invalid")
    if arguments.service_uid < 0:
        raise InstallContractError("operation_service_uid_invalid")

    output_root = absolute_canonical_directory(
        arguments.output_dir,
        "operation_output_root",
    )
    current_link = safe_absolute_unit_path(
        arguments.current_link,
        "current_link",
    )
    data_root = safe_absolute_unit_path(arguments.data_root, "data_root")
    backup_root = safe_absolute_unit_path(
        arguments.backup_root,
        "backup_root",
    )
    database_helper = safe_absolute_unit_path(
        arguments.database_helper,
        "database_helper",
    )
    systemctl_path = safe_absolute_unit_path(
        arguments.systemctl,
        "systemctl_path",
    )
    journalctl_path = safe_absolute_unit_path(
        arguments.journalctl,
        "journalctl_path",
    )
    public_origin = safe_public_origin(arguments.public_origin)
    instance = arguments.instance

    units = {
        f"{instance}-release-monitor.service": f"""\
[Unit]
Description=Kolibri V3 release monitor ({instance})
Wants=network-online.target
After=network-online.target
After={instance}-backend.service
After={instance}-frontend.service
After={instance}-product-run-worker.service
StartLimitIntervalSec=0

[Service]
Type=oneshot
User={arguments.service_user}
Group={arguments.service_group}
Environment=HOME=/nonexistent
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONUNBUFFERED=1
WorkingDirectory={current_link}/backend
ExecStart={current_link}/backend/venv/bin/python -m app.release_monitor \\
 --database {data_root}/kolibri-v3.db \\
 --backup-root {backup_root} \\
 --backup-owner-uid {arguments.service_uid} \\
 --backend-url http://127.0.0.1:{arguments.backend_port}/v1/ready \\
 --frontend-url http://127.0.0.1:{arguments.frontend_port}/api/health \\
 --public-url {public_origin}/readyz \\
 --release-id {arguments.release_id} \\
 --release-commit {arguments.release_commit} \\
 --expected-schema {arguments.expected_schema} \\
 --backend-unit {instance}-backend.service \\
 --frontend-unit {instance}-frontend.service \\
 --product-worker-unit {instance}-product-run-worker.service \\
 --backup-service-unit {instance}-database-backup.service \\
 --systemctl {systemctl_path} \\
 --journalctl {journalctl_path}
TimeoutStartSec=30s
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectHostname=true
ProtectClock=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
ProtectProc=invisible
ProcSubset=pid
RestrictSUIDSGID=true
RestrictNamespaces=true
RestrictRealtime=true
LockPersonality=true
CapabilityBoundingSet=
AmbientCapabilities=
SystemCallArchitectures=native
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadOnlyPaths={current_link} {backup_root}
ReadWritePaths={data_root}
""",
        f"{instance}-release-monitor.timer": f"""\
[Unit]
Description=Schedule Kolibri V3 release monitoring ({instance})

[Timer]
OnBootSec=2min
OnUnitActiveSec=60s
AccuracySec=5s
RandomizedDelaySec=5s
Persistent=true
Unit={instance}-release-monitor.service

[Install]
WantedBy=timers.target
""",
        f"{instance}-database-backup.service": f"""\
[Unit]
Description=Kolibri V3 verified SQLite backup ({instance})
After={instance}-backend.service
OnFailure={instance}-release-monitor.service
StartLimitIntervalSec=0

[Service]
Type=oneshot
User={arguments.service_user}
Group={arguments.service_group}
Environment=HOME=/nonexistent
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONUNBUFFERED=1
ExecStart={current_link}/backend/venv/bin/python {database_helper} scheduled-backup \\
 --source {data_root}/kolibri-v3.db \\
 --backup-root {backup_root} \\
 --release-id {arguments.release_id}
TimeoutStartSec=10min
UMask=0077
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
PrivateNetwork=true
ProtectSystem=strict
ProtectHome=true
ProtectHostname=true
ProtectClock=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
ProtectProc=invisible
ProcSubset=pid
RestrictSUIDSGID=true
RestrictNamespaces=true
RestrictRealtime=true
LockPersonality=true
CapabilityBoundingSet=
AmbientCapabilities=
SystemCallArchitectures=native
RestrictAddressFamilies=AF_UNIX
ReadOnlyPaths={current_link} {database_helper}
ReadWritePaths={data_root} {backup_root}
""",
        f"{instance}-database-backup.timer": f"""\
[Unit]
Description=Schedule Kolibri V3 verified SQLite backup ({instance})

[Timer]
OnCalendar=*-*-* 02:15:00 UTC
RandomizedDelaySec=10min
AccuracySec=1min
Persistent=true
Unit={instance}-database-backup.service

[Install]
WantedBy=timers.target
""",
    }
    for name, payload in units.items():
        validate_operation_unit(name, payload)
        atomic_write(output_root / name, payload, 0o644)
        print(f"operation_unit={output_root / name}")
    print("operation_render=ok")


def normalize_database(arguments: argparse.Namespace) -> None:
    data_root = absolute_canonical_directory(arguments.data_root, "data_root")
    if arguments.service_uid < 0 or arguments.service_gid < 0:
        raise InstallContractError("service_identity_invalid")
    database = data_root / "kolibri-v3.db"
    paths = (database, Path(f"{database}-wal"), Path(f"{database}-shm"))

    os.chown(data_root, arguments.service_uid, arguments.service_gid)
    os.chmod(data_root, 0o700)
    normalized: list[Path] = []
    for path in paths:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise InstallContractError(
                f"database_path_unreadable name={path.name}"
            ) from exc
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise InstallContractError(
                f"database_path_unsafe name={path.name}"
            )
        os.chown(path, arguments.service_uid, arguments.service_gid)
        os.chmod(path, 0o600)
        normalized.append(path)

    for path in normalized:
        metadata = path.stat()
        if (
            metadata.st_uid != arguments.service_uid
            or metadata.st_gid != arguments.service_gid
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise InstallContractError(
                f"database_permission_convergence_failed name={path.name}"
            )
    root_metadata = data_root.stat()
    if (
        root_metadata.st_uid != arguments.service_uid
        or root_metadata.st_gid != arguments.service_gid
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
    ):
        raise InstallContractError("data_root_permission_convergence_failed")
    print(f"database_files_normalized={len(normalized)}")
    print("database_permissions=ok")


def trusted_regular_file(
    raw_path: str,
    label: str,
    *,
    expected_uid: int,
    expected_mode: int,
) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        raise InstallContractError(f"{label}_not_absolute")
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise InstallContractError(f"{label}_unavailable") from exc
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or resolved != path
    ):
        raise InstallContractError(f"{label}_unsafe")
    if (
        metadata.st_uid != expected_uid
        or stat.S_IMODE(metadata.st_mode) != expected_mode
    ):
        raise InstallContractError(f"{label}_permissions_invalid")
    return path


def parse_environment_file(path: Path) -> dict[str, str]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise InstallContractError("workers_environment_unreadable") from exc
    if len(payload) > 128 * 1024:
        raise InstallContractError("workers_environment_too_large")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InstallContractError(
            "workers_environment_encoding_invalid"
        ) from exc

    environment: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in raw_line:
            raise InstallContractError(
                f"workers_environment_line_invalid line={line_number}"
            )
        key, value = raw_line.split("=", 1)
        if (
            not ENVIRONMENT_KEY_PATTERN.fullmatch(key)
            or value != value.strip()
            or any(character in value for character in "\r\n\0")
        ):
            raise InstallContractError(
                f"workers_environment_line_invalid line={line_number}"
            )
        if key in environment:
            raise InstallContractError(
                f"workers_environment_key_duplicate key={key}"
            )
        environment[key] = value
    return environment


def validate_command_url(value: str, key: str) -> None:
    if not value:
        raise InstallContractError(f"worker_endpoint_missing key={key}")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise InstallContractError(
            f"worker_endpoint_invalid key={key}"
        ) from exc
    loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.query
        or parsed.path in {"", "/"}
        or (parsed.scheme == "http" and not loopback)
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise InstallContractError(f"worker_endpoint_invalid key={key}")


def validate_worker_credential(
    credentials_root: Path,
    name: str,
    expected_uid: int,
) -> None:
    path = trusted_regular_file(
        os.fspath(credentials_root / name),
        f"worker_credential_{name}",
        expected_uid=expected_uid,
        expected_mode=0o600,
    )
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise InstallContractError(
            f"worker_credential_{name}_unreadable"
        ) from exc
    if not 16 <= size <= 64 * 1024:
        raise InstallContractError(
            f"worker_credential_{name}_size_invalid"
        )


def validate_worker_enablement(arguments: argparse.Namespace) -> None:
    if arguments.expected_uid < 0:
        raise InstallContractError("worker_expected_uid_invalid")
    workers_environment = trusted_regular_file(
        arguments.workers_env,
        "workers_environment",
        expected_uid=arguments.expected_uid,
        expected_mode=0o600,
    )
    credentials_root = absolute_canonical_directory(
        arguments.credentials_root,
        "worker_credentials_root",
    )
    credentials_metadata = credentials_root.stat()
    if (
        credentials_metadata.st_uid != arguments.expected_uid
        or stat.S_IMODE(credentials_metadata.st_mode) != 0o700
    ):
        raise InstallContractError(
            "worker_credentials_root_permissions_invalid"
        )

    environment = parse_environment_file(workers_environment)
    required_urls = (
        PRODUCT_WORKER_KEYS
        if arguments.kind == "product"
        else PROVIDER_WORKER_KEYS
    )
    for key in required_urls:
        validate_command_url(environment.get(key, ""), key)
    if (
        arguments.kind == "provider"
        and environment.get(
            "KOLIBRI_V3_PROVIDER_AUTHORITY_DISPATCH_CONFIGURED"
        )
        != "true"
    ):
        raise InstallContractError(
            "provider_authority_dispatch_not_configured"
        )
    for credential_name in WORKER_CREDENTIALS[arguments.kind]:
        validate_worker_credential(
            credentials_root,
            credential_name,
            arguments.expected_uid,
        )
    print(f"worker_preflight={arguments.kind}")
    print("worker_enablement=ok")


def unquote_environment_value(value: str) -> str:
    if (
        len(value) >= 2
        and value[0] == value[-1]
        and value[0] in {"'", '"'}
    ):
        return value[1:-1]
    return value


def validate_operator_backend_environment(
    arguments: argparse.Namespace,
) -> None:
    path = Path(arguments.backend_env)
    if not path.exists() and not path.is_symlink():
        if not arguments.allow_missing:
            raise InstallContractError(
                "operator_backend_environment_unavailable"
            )
        print("operator_backend_environment=absent_safe")
        return
    backend_environment = trusted_regular_file(
        arguments.backend_env,
        "operator_backend_environment",
        expected_uid=arguments.expected_uid,
        expected_mode=0o600,
    )
    environment = parse_environment_file(backend_environment)
    raw_developer_flag = environment.get(
        "KOLIBRI_V3_DEVELOPER_AGENT_ENABLED"
    )
    if raw_developer_flag is not None:
        normalized = unquote_environment_value(
            raw_developer_flag
        ).strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            raise InstallContractError(
                "embedded_developer_agent_forbidden_in_production"
            )
        if normalized not in {"0", "false", "no", "off"}:
            raise InstallContractError(
                "operator_developer_agent_flag_invalid"
            )
    print("operator_backend_environment=production_safe")


def parser() -> argparse.ArgumentParser:
    contract_parser = argparse.ArgumentParser(
        description="Prepare fail-closed Kolibri V3 host release inputs."
    )
    commands = contract_parser.add_subparsers(dest="command", required=True)

    render_parser = commands.add_parser("render-workers")
    render_parser.add_argument("--source-root", required=True)
    render_parser.add_argument("--output-dir", required=True)
    render_parser.add_argument("--instance", required=True)
    render_parser.add_argument("--install-root", required=True)
    render_parser.add_argument("--config-root", required=True)
    render_parser.add_argument("--service-user", required=True)
    render_parser.add_argument("--service-group", required=True)
    render_parser.add_argument("--backend-service", required=True)
    render_parser.set_defaults(handler=render_workers)

    operation_parser = commands.add_parser("render-operations")
    operation_parser.add_argument("--output-dir", required=True)
    operation_parser.add_argument("--instance", required=True)
    operation_parser.add_argument("--current-link", required=True)
    operation_parser.add_argument("--service-user", required=True)
    operation_parser.add_argument("--service-group", required=True)
    operation_parser.add_argument("--service-uid", required=True, type=int)
    operation_parser.add_argument("--data-root", required=True)
    operation_parser.add_argument("--backup-root", required=True)
    operation_parser.add_argument("--backend-port", required=True, type=int)
    operation_parser.add_argument("--frontend-port", required=True, type=int)
    operation_parser.add_argument("--public-origin", required=True)
    operation_parser.add_argument("--release-id", required=True)
    operation_parser.add_argument("--release-commit", required=True)
    operation_parser.add_argument("--expected-schema", required=True, type=int)
    operation_parser.add_argument("--systemctl", required=True)
    operation_parser.add_argument("--journalctl", required=True)
    operation_parser.add_argument("--database-helper", required=True)
    operation_parser.set_defaults(handler=render_operations)

    database_parser = commands.add_parser("normalize-database")
    database_parser.add_argument("--data-root", required=True)
    database_parser.add_argument("--service-uid", required=True, type=int)
    database_parser.add_argument("--service-gid", required=True, type=int)
    database_parser.set_defaults(handler=normalize_database)

    worker_parser = commands.add_parser("validate-worker-enablement")
    worker_parser.add_argument(
        "--kind",
        required=True,
        choices=tuple(WORKER_CREDENTIALS),
    )
    worker_parser.add_argument("--workers-env", required=True)
    worker_parser.add_argument("--credentials-root", required=True)
    worker_parser.add_argument("--expected-uid", required=True, type=int)
    worker_parser.set_defaults(handler=validate_worker_enablement)

    backend_environment_parser = commands.add_parser(
        "validate-operator-backend-env"
    )
    backend_environment_parser.add_argument("--backend-env", required=True)
    backend_environment_parser.add_argument(
        "--expected-uid",
        required=True,
        type=int,
    )
    backend_environment_parser.add_argument(
        "--allow-missing",
        action="store_true",
    )
    backend_environment_parser.set_defaults(
        handler=validate_operator_backend_environment
    )
    return contract_parser


def main() -> int:
    arguments = parser().parse_args()
    try:
        arguments.handler(arguments)
    except InstallContractError as exc:
        fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
