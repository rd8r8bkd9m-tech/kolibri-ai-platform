#!/usr/bin/env python3
"""Safely unload the Mac Codex provider while preserving user data and auth."""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from mac_codex_provider_common import (  # noqa: E402
    LABEL,
    MANAGED_MARKER,
    MacProviderConfigError,
    MacProviderLayout,
    json_line,
    launchctl,
)


def validate_managed_plist(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_symlink() or not path.is_file():
        raise MacProviderConfigError("launch_agent_path_unsafe")
    try:
        payload = plistlib.loads(path.read_bytes())
    except (plistlib.InvalidFileException, ValueError) as exc:
        raise MacProviderConfigError("launch_agent_plist_invalid") from exc
    if (
        payload.get("Label") != LABEL
        or payload.get("KolibriManagedContract") != "kolibri.mac-codex-provider.launchagent.v1"
    ):
        raise MacProviderConfigError("launch_agent_not_managed")
    return True


def remove_managed_runtime(layout: MacProviderLayout) -> bool:
    runtime_root = layout.releases.parent
    if not runtime_root.exists():
        return False
    if runtime_root.is_symlink() or not runtime_root.is_dir():
        raise MacProviderConfigError("runtime_root_unsafe")
    if not layout.releases.exists():
        return False
    if layout.releases.is_symlink() or not layout.releases.is_dir():
        raise MacProviderConfigError("runtime_releases_unsafe")
    for release in layout.releases.iterdir():
        if release.is_symlink() or not release.is_dir():
            raise MacProviderConfigError("runtime_release_unsafe")
        marker = release / MANAGED_MARKER
        if not marker.is_file() or marker.is_symlink() or marker.read_text(encoding="utf-8").strip() != LABEL:
            raise MacProviderConfigError("runtime_release_not_managed")
    # Remove only the directory whose children were all proven managed. Never
    # recurse over the parent: it may contain a future user-owned runtime item.
    shutil.rmtree(layout.releases)
    try:
        runtime_root.rmdir()
    except OSError:
        pass
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--remove-runtime",
        action="store_true",
        help="remove only checksum-addressed managed runtime; preserve config, logs, tasks, and artifacts",
    )
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        raise MacProviderConfigError("launch_agent_must_uninstall_as_current_user")
    layout = MacProviderLayout.from_home(Path.home())
    installed = validate_managed_plist(layout.launch_agent)
    plan = {
        "status": "validated",
        "apply": args.apply,
        "label": LABEL,
        "launch_agent_present": installed,
        "remove_runtime": args.remove_runtime,
        "preserved": [
            "codex_session", "mesh_manifest", "runner_access",
            "external_provider_credential", "worktrees", "artifacts", "logs",
        ],
    }
    if not args.apply:
        print(json_line(plan))
        return 0

    service = f"gui/{os.geteuid()}/{LABEL}"
    launchctl(["bootout", service], tolerate_missing=True)
    if installed:
        layout.launch_agent.unlink()
    runtime_removed = remove_managed_runtime(layout) if args.remove_runtime else False
    plan.update({
        "status": "uninstalled",
        "launch_agent_present": False,
        "runtime_removed": runtime_removed,
    })
    print(json_line(plan))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MacProviderConfigError as exc:
        print(json_line({"status": "failed", "error": exc.code}))
        raise SystemExit(1)
