#!/usr/bin/env python3
"""Create a release marker only inside an isolated snapshot directory."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
from pathlib import Path


SAFE_RELEASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
MARKER_NAME = "RELEASE_ID"


class SnapshotMarkerError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def create_release_marker(root: Path, release_id: str) -> Path:
    """Atomically add ``RELEASE_ID`` without touching a Git worktree."""

    normalized_id = str(release_id or "").strip()
    if not SAFE_RELEASE_ID.fullmatch(normalized_id):
        raise SnapshotMarkerError("release_snapshot_id_invalid")
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise SnapshotMarkerError("release_snapshot_root_invalid") from exc
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise SnapshotMarkerError("release_snapshot_root_invalid")
    root = root.resolve(strict=True)
    if (root / ".git").exists():
        raise SnapshotMarkerError("release_snapshot_git_worktree_forbidden")

    marker = root / MARKER_NAME
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(marker, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(f"{normalized_id}\n".encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
        marker.chmod(0o644)
    except FileExistsError as exc:
        raise SnapshotMarkerError("release_snapshot_marker_exists") from exc
    except OSError as exc:
        try:
            marker.unlink()
        except FileNotFoundError:
            pass
        raise SnapshotMarkerError("release_snapshot_marker_write_failed") from exc
    return marker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--release-id", required=True)
    args = parser.parse_args(argv)
    try:
        create_release_marker(args.root, args.release_id)
    except SnapshotMarkerError as exc:
        print(json.dumps({"status": "failed", "error_type": exc.code}, sort_keys=True))
        return 2
    print(json.dumps({
        "schema_version": "kolibri.release-snapshot-marker.v1",
        "status": "created",
        "release_id": args.release_id,
        "marker": MARKER_NAME,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
