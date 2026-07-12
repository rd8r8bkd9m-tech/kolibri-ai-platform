#!/usr/bin/env python3
"""Streamable, read-only preflight for one manifest-selected worker.

The controller sends this source over SSH in dry-run mode.  It receives only
the expected node ID, mesh address and digest of normalized public trust; no
key body, token or private material is accepted or emitted.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import pwd
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "kolibri.worker-release-authority-preflight.v1"
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
NODE_ID = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?\Z")
MAX_FILE_BYTES = 32 * 1024 * 1024
MANAGED_FILES = (
    "/etc/kolibri/release_allowed_signers",
    "/etc/kolibri/owner_allowed_signers",
    "/etc/kolibri/release-policy.json",
    "/usr/local/lib/kolibri/release_authority.py",
    "/usr/local/lib/kolibri/release_helper.py",
    "/usr/local/lib/kolibri/release_installer.py",
    "/usr/local/lib/kolibri/worker_release_health.py",
    "/etc/systemd/system/kolibri-release-helper.service",
    "/etc/systemd/system/kolibri-release-helper.socket",
)
MANAGED_DIRECTORIES = (
    "/usr/local/lib/kolibri",
    "/etc/kolibri",
    "/var/lib/kolibri-release",
    "/var/lib/kolibri-release/artifacts",
    "/opt/kolibri-ai",
    "/opt/kolibri-ai/releases",
    "/run/kolibri-release",
)
REQUIRED_PARENTS = (
    "/usr/local/lib",
    "/etc",
    "/etc/systemd/system",
    "/var/lib",
    "/opt",
    "/var/backups",
    "/run/lock",
)


class PreflightError(RuntimeError):
    """Stable preflight failure without host details."""


def _regular_digest(path: Path) -> str:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            value = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(value.st_mode)
                or value.st_nlink != 1
                or value.st_uid != 0
                or stat.S_IMODE(value.st_mode) & 0o022
                or not 0 < value.st_size <= MAX_FILE_BYTES
            ):
                raise PreflightError("worker_release_managed_path_unsafe")
            payload = handle.read(MAX_FILE_BYTES + 1)
        if len(payload) > MAX_FILE_BYTES:
            raise PreflightError("worker_release_managed_path_unsafe")
    except PreflightError:
        raise
    except OSError as exc:
        raise PreflightError("worker_release_managed_path_unsafe") from exc
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _local_addresses() -> set[str]:
    try:
        completed = subprocess.run(
            ["/usr/sbin/ip", "-4", "-o", "addr", "show"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PreflightError("worker_release_identity_probe_failed") from exc
    if completed.returncode != 0:
        raise PreflightError("worker_release_identity_probe_failed")
    return {
        field.split("/", 1)[0]
        for line in completed.stdout.splitlines()
        for field in line.split()
        if "/" in field
    }


def _check_parents() -> None:
    for logical in REQUIRED_PARENTS:
        try:
            value = Path(logical).lstat()
        except OSError as exc:
            raise PreflightError("worker_release_parent_unavailable") from exc
        mode = stat.S_IMODE(value.st_mode)
        if (
            not stat.S_ISDIR(value.st_mode)
            or value.st_uid != 0
            or (
                logical == "/run/lock"
                and mode != 0o1777
            )
            or (
                logical != "/run/lock"
                and mode & 0o022
            )
        ):
            raise PreflightError("worker_release_parent_unsafe")


def _check_types() -> None:
    for logical in MANAGED_FILES:
        path = Path(logical)
        if os.path.lexists(path) and not stat.S_ISREG(path.lstat().st_mode):
            raise PreflightError("worker_release_managed_path_unsafe")
    for logical in MANAGED_DIRECTORIES:
        path = Path(logical)
        if os.path.lexists(path) and not stat.S_ISDIR(path.lstat().st_mode):
            raise PreflightError("worker_release_managed_path_unsafe")


def _check_current() -> str:
    current = Path("/opt/kolibri-ai/current")
    releases = Path("/opt/kolibri-ai/releases")
    if not os.path.lexists(current):
        return "absent"
    if not current.is_symlink() or not releases.is_dir():
        raise PreflightError("worker_release_current_unsafe")
    try:
        selected = current.resolve(strict=True)
        root = releases.resolve(strict=True)
    except OSError as exc:
        raise PreflightError("worker_release_current_unsafe") from exc
    if selected.parent != root or not selected.is_dir():
        raise PreflightError("worker_release_current_unsafe")
    return "contained"


def preflight(
    target_node: str,
    target_ip: str,
    expected_trust_digest: str,
    *,
    local_addresses: set[str] | None = None,
) -> dict[str, Any]:
    if (
        not NODE_ID.fullmatch(target_node)
        or target_node == "home"
        or not SHA256.fullmatch(expected_trust_digest)
    ):
        raise PreflightError("worker_release_preflight_arguments_invalid")
    try:
        address = ipaddress.ip_address(target_ip)
    except ValueError as exc:
        raise PreflightError("worker_release_preflight_arguments_invalid") from exc
    if address.version != 4 or address.is_loopback or address.is_unspecified:
        raise PreflightError("worker_release_preflight_arguments_invalid")
    if str(address) not in (local_addresses if local_addresses is not None else _local_addresses()):
        raise PreflightError("worker_release_target_identity_mismatch")
    try:
        pwd.getpwnam("kolibri-agent")
    except KeyError as exc:
        raise PreflightError("worker_release_agent_identity_missing") from exc
    _check_parents()
    _check_types()
    current = _check_current()
    trust: dict[str, str] = {}
    for logical in (
        "/etc/kolibri/release_allowed_signers",
        "/etc/kolibri/owner_allowed_signers",
    ):
        path = Path(logical)
        if not os.path.lexists(path):
            trust[path.name] = "absent"
        elif _regular_digest(path) == expected_trust_digest:
            trust[path.name] = "matching"
        else:
            raise PreflightError("worker_release_existing_trust_conflict")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "read_only_preflight_ok",
        "target_node": target_node,
        "current_target": current,
        "trust": trust,
        "control_plane_restart": False,
        "backend_restart": False,
    }


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(arguments) != 3:
            raise PreflightError("worker_release_preflight_arguments_invalid")
        result = preflight(arguments[0], arguments[1], arguments[2])
        print(json.dumps(result, sort_keys=True))
        return 0
    except PreflightError as exc:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "failed",
                    "error_code": str(exc),
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
