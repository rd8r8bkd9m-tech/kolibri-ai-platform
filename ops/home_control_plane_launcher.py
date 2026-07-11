#!/usr/bin/env python3
"""Stable Home-only launcher for the immutable Factory Control Plane.

The one-time authority bootstrap installs this small launcher and a systemd
drop-in.  Before the first unified release it may use the exact legacy source
path; as soon as ``/opt/kolibri-ai/current`` contains the complete Control
Plane profile, every restart selects that immutable release instead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path

try:
    from ops.control_plane_endpoint import assert_local_home_control_plane
except ImportError:  # installed beside the resolver
    from control_plane_endpoint import assert_local_home_control_plane


CURRENT_LINK = Path("/opt/kolibri-ai/current")
RELEASE_ROOT = Path("/opt/kolibri-ai/releases")
LEGACY_ROOT = Path("/opt/kolibri-ai-platform")
PYTHON = Path("/usr/bin/python3")
REQUIRED_RUNTIME = (
    "ops/control_plane_endpoint.py",
    "ops/factory_control.py",
    "ops/fleet_membership.py",
    "ops/release_authority.py",
    "ops/telegram_superfactory.py",
)
IMMUTABLE_PROFILE_SENTINELS = frozenset({
    "ops/agent_host.py",
    "ops/factory_control.py",
})
MAX_MANIFEST_BYTES = 2 * 1024 * 1024


class LauncherError(RuntimeError):
    """Stable fail-closed launcher error without path or secret disclosure."""


def _trusted_regular(path: Path, *, executable: bool = False) -> bool:
    try:
        value = path.lstat()
    except OSError:
        return False
    if (
        stat.S_ISLNK(value.st_mode)
        or not stat.S_ISREG(value.st_mode)
        or value.st_nlink != 1
        or value.st_size <= 0
        or value.st_mode & 0o022
    ):
        return False
    if os.geteuid() == 0 and value.st_uid != 0:
        return False
    return not executable or bool(value.st_mode & 0o111)


def _immutable_root() -> Path | None:
    if not os.path.lexists(CURRENT_LINK):
        return None
    try:
        releases = RELEASE_ROOT.resolve(strict=True)
        current = CURRENT_LINK.resolve(strict=True)
        current_value = CURRENT_LINK.lstat()
        release_value = current.lstat()
    except OSError as exc:
        raise LauncherError("immutable_control_plane_release_unsafe") from exc
    if (
        not stat.S_ISLNK(current_value.st_mode)
        or current.parent != releases
        or not stat.S_ISDIR(release_value.st_mode)
        or release_value.st_mode & 0o022
        or (os.geteuid() == 0 and release_value.st_uid != 0)
    ):
        raise LauncherError("immutable_control_plane_release_unsafe")

    manifest_path = current / ".kolibri-release/manifest.json"
    if (
        not _trusted_regular(manifest_path)
        or manifest_path.stat().st_size > MAX_MANIFEST_BYTES
    ):
        raise LauncherError("immutable_control_plane_manifest_invalid")
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw)
        canonical = json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise LauncherError("immutable_control_plane_manifest_invalid") from exc
    if (
        not 0 < len(raw) <= MAX_MANIFEST_BYTES
        or canonical != raw
        or not isinstance(manifest, dict)
        or manifest.get("release_id") != current.name
        or not isinstance(manifest.get("files"), list)
    ):
        raise LauncherError("immutable_control_plane_manifest_invalid")
    records: dict[str, dict[str, object]] = {}
    for item in manifest["files"]:
        if not isinstance(item, dict):
            raise LauncherError("immutable_control_plane_manifest_invalid")
        path = str(item.get("path") or "")
        if not path or path in records:
            raise LauncherError("immutable_control_plane_manifest_invalid")
        records[path] = item
    if not IMMUTABLE_PROFILE_SENTINELS.intersection(records):
        # One explicit migration exception: a signed product-only release may
        # predate both immutable Agent Host and Factory Control runtimes.
        return None
    if not set(REQUIRED_RUNTIME).issubset(records):
        raise LauncherError("immutable_control_plane_runtime_incomplete")
    for relative in REQUIRED_RUNTIME:
        path = current / relative
        record = records[relative]
        if not _trusted_regular(path):
            raise LauncherError("immutable_control_plane_runtime_incomplete")
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise LauncherError("immutable_control_plane_runtime_invalid") from exc
        if (
            record.get("sha256") != hashlib.sha256(payload).hexdigest()
            or record.get("size_bytes") != len(payload)
        ):
            raise LauncherError("immutable_control_plane_runtime_invalid")
    return current


def select_runtime() -> tuple[Path, str, str]:
    immutable = _immutable_root()
    if immutable is not None:
        return immutable, immutable.name, "immutable-release"
    if not all(_trusted_regular(LEGACY_ROOT / relative) for relative in REQUIRED_RUNTIME):
        raise LauncherError("control_plane_runtime_unavailable")
    return LEGACY_ROOT, "legacy-bootstrap", "legacy-bootstrap"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-selection", action="store_true")
    args, runtime_args = parser.parse_known_args(argv)
    assert_local_home_control_plane()
    root, release_id, source = select_runtime()
    if args.print_selection:
        print(json.dumps({
            "status": "selected",
            "authority": "home",
            "release_id": release_id,
            "source": source,
        }, sort_keys=True))
        return 0
    if not _trusted_regular(PYTHON, executable=True):
        raise LauncherError("control_plane_python_unavailable")
    environment = dict(os.environ)
    environment.update({
        "KOLIBRI_REPO_ROOT": str(root),
        "KOLIBRI_OPS_DIR": str(root / "ops"),
        "KOLIBRI_ACTIVE_RELEASE_ID": release_id,
        "FACTORY_CANARY_READ_ONLY": "0",
        "PYTHONPATH": f"{root / 'ops'}:{root}",
        "PYTHONNOUSERSITE": "1",
    })
    os.execve(
        str(PYTHON),
        [str(PYTHON), str(root / "ops/factory_control.py"), *runtime_args],
        environment,
    )
    return 70  # pragma: no cover - os.execve never returns


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        raise SystemExit(str(exc) if isinstance(exc, LauncherError) else "control_plane_launcher_failed")
