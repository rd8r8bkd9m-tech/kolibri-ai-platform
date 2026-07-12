#!/usr/bin/env python3
"""Dry-run-first deletion of one explicitly identified runtime pollutant.

The cleanup never accepts globs.  It binds every candidate to basename, owner,
size, SHA-256, inode and device, then requires the scan digest to be supplied
back for ``--apply``.  Symlinks, hardlinks and files changed after the scan are
skipped rather than guessed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "kolibri.exact-runtime-cleanup.v1"
DEFAULT_ROOT = Path("/tmp")
DEFAULT_BASENAME = "libopentui.so"
DEFAULT_SIZE = 4_499_072
DEFAULT_SHA256 = "4e9743322dc1c34098e3b530eb5bb80983b03bbf331fb74857b3b1aef484737a"
MAX_CANDIDATES = 10_000


class CleanupError(RuntimeError):
    pass


def _digest_fd(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while chunk := os.read(descriptor, 1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def _candidate(path: Path, *, uid: int, size: int, sha256: str) -> dict[str, Any] | None:
    try:
        parent = path.parent.lstat()
        value = path.lstat()
        if (
            not stat.S_ISDIR(parent.st_mode)
            or stat.S_ISLNK(parent.st_mode)
            or parent.st_uid != uid
            or parent.st_mode & 0o022
            or
            not stat.S_ISREG(value.st_mode)
            or stat.S_ISLNK(value.st_mode)
            or value.st_nlink != 1
            or value.st_uid != uid
            or value.st_size != size
        ):
            return None
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (value.st_dev, value.st_ino):
                return None
            if _digest_fd(descriptor) != sha256:
                return None
        finally:
            os.close(descriptor)
        return {
            "path": str(path),
            "device": value.st_dev,
            "inode": value.st_ino,
            "ctime_ns": value.st_ctime_ns,
            "mtime_ns": value.st_mtime_ns,
            "uid": value.st_uid,
            "size": value.st_size,
            "sha256": sha256,
        }
    except OSError:
        return None


def scan(
    root: Path,
    *,
    basename: str = DEFAULT_BASENAME,
    uid: int = 0,
    size: int = DEFAULT_SIZE,
    sha256: str = DEFAULT_SHA256,
) -> dict[str, Any]:
    if not basename or "/" in basename or "\x00" in basename:
        raise CleanupError("cleanup_basename_invalid")
    if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
        raise CleanupError("cleanup_sha256_invalid")
    try:
        root_value = root.lstat()
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise CleanupError("cleanup_root_unavailable") from exc
    if not stat.S_ISDIR(root_value.st_mode) or stat.S_ISLNK(root_value.st_mode):
        raise CleanupError("cleanup_root_unsafe")
    candidates: list[dict[str, Any]] = []
    for directory, names, files in os.walk(resolved, followlinks=False):
        names[:] = [
            name for name in names
            if not Path(directory, name).is_symlink()
        ]
        if basename not in files:
            continue
        item = _candidate(Path(directory, basename), uid=uid, size=size, sha256=sha256)
        if item is not None:
            candidates.append(item)
            if len(candidates) > MAX_CANDIDATES:
                raise CleanupError("cleanup_candidate_limit_exceeded")
    candidates.sort(key=lambda item: item["path"])
    binding = hashlib.sha256(json.dumps(
        candidates,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "planned",
        "mutation": "none",
        "root": str(resolved),
        "basename": basename,
        "required_uid": uid,
        "required_size": size,
        "required_sha256": sha256,
        "candidate_count": len(candidates),
        "candidate_bytes": len(candidates) * size,
        "scan_digest": binding,
        "candidates": candidates,
    }


def apply(plan: dict[str, Any], *, ack_digest: str) -> dict[str, Any]:
    if ack_digest != plan.get("scan_digest"):
        raise CleanupError("cleanup_scan_ack_mismatch")
    removed: list[str] = []
    skipped: list[str] = []
    for item in plan.get("candidates") or []:
        path = Path(item["path"])
        current = _candidate(
            path,
            uid=int(item["uid"]),
            size=int(item["size"]),
            sha256=str(item["sha256"]),
        )
        if current is None or (
            current["device"],
            current["inode"],
            current["ctime_ns"],
            current["mtime_ns"],
        ) != (
            item.get("device"),
            item.get("inode"),
            item.get("ctime_ns"),
            item.get("mtime_ns"),
        ):
            skipped.append(str(path))
            continue
        try:
            os.unlink(path)
            removed.append(str(path))
        except OSError:
            skipped.append(str(path))
    return {
        **{key: value for key, value in plan.items() if key != "candidates"},
        "status": "completed" if not skipped else "partial",
        "mutation": "exact_files_removed",
        "removed_count": len(removed),
        "removed_bytes": len(removed) * int(plan["required_size"]),
        "skipped_count": len(skipped),
        "removed": removed,
        "skipped": skipped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--basename", default=DEFAULT_BASENAME)
    parser.add_argument("--uid", type=int, default=0)
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE)
    parser.add_argument("--sha256", default=DEFAULT_SHA256)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--ack-digest")
    args = parser.parse_args(argv)
    try:
        result = scan(
            args.root,
            basename=args.basename,
            uid=args.uid,
            size=args.size,
            sha256=args.sha256,
        )
        if args.apply:
            result = apply(result, ack_digest=str(args.ack_digest or ""))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] in {"planned", "completed"} else 2
    except CleanupError as exc:
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "reason": str(exc),
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
