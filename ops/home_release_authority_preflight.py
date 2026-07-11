#!/usr/bin/env python3
"""Read-only remote preflight for the Home release authority bootstrap.

The operator wrapper streams this program to Home over SSH; it is never
installed.  It receives only a digest of normalized public trust, never the
public-key body.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "kolibri.home-release-authority-preflight.v1"
SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
MAX_TRUST_BYTES = 32 * 1024
MANAGED_FILES = (
    "/etc/kolibri/release_allowed_signers",
    "/etc/kolibri/owner_allowed_signers",
    "/etc/kolibri/release-policy.json",
    "/usr/local/lib/kolibri/release_authority.py",
    "/usr/local/lib/kolibri/release_helper.py",
    "/usr/local/lib/kolibri/release_installer.py",
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
)
REQUIRED_PARENT_DIRECTORIES = (
    "/usr/local/lib",
    "/etc",
    "/etc/systemd/system",
    "/var/lib",
    "/opt",
    "/var/backups",
    "/run/lock",
)


class PreflightError(RuntimeError):
    pass


def _rooted(root: Path, logical: str) -> Path:
    return root / Path(logical).relative_to("/")


def _regular_digest(path: Path, *, owner_uid: int) -> str:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            value = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(value.st_mode)
                or value.st_nlink != 1
                or not 0 < value.st_size <= MAX_TRUST_BYTES
                or value.st_uid != owner_uid
                or stat.S_IMODE(value.st_mode) & 0o022
            ):
                raise PreflightError("release_authority_existing_trust_unsafe")
            payload = handle.read(MAX_TRUST_BYTES + 1)
        if len(payload) > MAX_TRUST_BYTES:
            raise PreflightError("release_authority_existing_trust_unsafe")
    except PreflightError:
        raise
    except OSError as exc:
        raise PreflightError("release_authority_existing_trust_unsafe") from exc
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _check_managed_types(root: Path) -> None:
    for logical in MANAGED_FILES:
        path = _rooted(root, logical)
        if not os.path.lexists(path):
            continue
        try:
            value = path.lstat()
        except OSError as exc:
            raise PreflightError("release_authority_managed_path_unsafe") from exc
        if not stat.S_ISREG(value.st_mode):
            raise PreflightError("release_authority_managed_path_unsafe")
    for logical in MANAGED_DIRECTORIES:
        path = _rooted(root, logical)
        if not os.path.lexists(path):
            continue
        try:
            value = path.lstat()
        except OSError as exc:
            raise PreflightError("release_authority_managed_path_unsafe") from exc
        if not stat.S_ISDIR(value.st_mode):
            raise PreflightError("release_authority_managed_path_unsafe")


def _check_required_parents(root: Path) -> None:
    production_root = root == Path("/")
    for logical in REQUIRED_PARENT_DIRECTORIES:
        path = _rooted(root, logical)
        try:
            value = path.lstat()
        except OSError as exc:
            raise PreflightError("release_authority_parent_unavailable") from exc
        if not stat.S_ISDIR(value.st_mode):
            raise PreflightError("release_authority_parent_unsafe")
        if not production_root:
            continue
        mode = stat.S_IMODE(value.st_mode)
        if value.st_uid != 0:
            raise PreflightError("release_authority_parent_unsafe")
        if logical == "/run/lock":
            if mode != 0o1777:
                raise PreflightError("release_authority_parent_unsafe")
        elif mode & 0o022:
            raise PreflightError("release_authority_parent_unsafe")


def _check_current(root: Path) -> str:
    releases = _rooted(root, "/opt/kolibri-ai/releases")
    current = _rooted(root, "/opt/kolibri-ai/current")
    if not os.path.lexists(current):
        return "absent"
    if not current.is_symlink() or not releases.is_dir():
        raise PreflightError("release_current_link_unsafe")
    try:
        releases_value = releases.lstat()
        resolved_releases = releases.resolve(strict=True)
        resolved_target = current.resolve(strict=True)
    except OSError as exc:
        raise PreflightError("release_current_link_unsafe") from exc
    if (
        not stat.S_ISDIR(releases_value.st_mode)
        or resolved_target.parent != resolved_releases
        or not resolved_target.is_dir()
    ):
        raise PreflightError("release_current_link_unsafe")
    return "contained"


def _check_backup_boundary(root: Path) -> None:
    base = _rooted(root, "/var/backups")
    try:
        base_value = base.lstat()
    except OSError as exc:
        raise PreflightError("release_authority_backup_unsafe") from exc
    if (
        not stat.S_ISDIR(base_value.st_mode)
        or (root == Path("/") and base_value.st_uid != 0)
        or stat.S_IMODE(base_value.st_mode) & 0o022
    ):
        raise PreflightError("release_authority_backup_unsafe")
    cursor = base
    for part in ("kolibri", "release-authority"):
        cursor = cursor / part
        if not os.path.lexists(cursor):
            continue
        try:
            value = cursor.lstat()
        except OSError as exc:
            raise PreflightError("release_authority_backup_unsafe") from exc
        if (
            not stat.S_ISDIR(value.st_mode)
            or (root == Path("/") and value.st_uid != 0)
            or stat.S_IMODE(value.st_mode) & 0o022
        ):
            raise PreflightError("release_authority_backup_unsafe")


def preflight(expected_trust_digest: str, *, root: Path = Path("/")) -> dict[str, Any]:
    if not SHA256.fullmatch(expected_trust_digest):
        raise PreflightError("signer_public_key_digest_invalid")
    _check_required_parents(root)
    _check_managed_types(root)
    current = _check_current(root)
    _check_backup_boundary(root)
    trust_state: dict[str, str] = {}
    owner_uid = 0 if root == Path("/") else os.geteuid()
    for logical in (
        "/etc/kolibri/release_allowed_signers",
        "/etc/kolibri/owner_allowed_signers",
    ):
        path = _rooted(root, logical)
        if not os.path.lexists(path):
            trust_state[Path(logical).name] = "absent"
            continue
        if _regular_digest(path, owner_uid=owner_uid) != expected_trust_digest:
            raise PreflightError("release_authority_existing_trust_conflict")
        trust_state[Path(logical).name] = "matching"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "read_only_preflight_ok",
        "current_target": current,
        "trust": trust_state,
    }


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        result = {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "error_code": "release_authority_preflight_arguments_invalid",
        }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    try:
        result = preflight(arguments[0])
    except PreflightError as exc:
        result = {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "error_code": str(exc),
        }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
