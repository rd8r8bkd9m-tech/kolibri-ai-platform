#!/usr/bin/env python3
"""Fail-closed filesystem health checks for worker-only runtime releases.

The release policy calls this program directly with fixed argv.  It never
executes payload code.  Candidate and current checks validate only the two
signed Agent Host payloads and the release marker that are required before a
worker can re-enter through the immutable ``current`` link.
"""

from __future__ import annotations

import argparse
import os
import pwd
import stat
from pathlib import Path


REQUIRED_PAYLOADS = (
    "ops/agent_host.py",
    "ops/mimo/kolibri-response-only.md",
)


class WorkerReleaseHealthError(RuntimeError):
    """Stable error boundary; details are intentionally not emitted."""


def _trusted_directory(path: Path, *, owner_uid: int) -> None:
    try:
        value = path.lstat()
    except OSError as exc:
        raise WorkerReleaseHealthError("worker_release_directory_unavailable") from exc
    if (
        not stat.S_ISDIR(value.st_mode)
        or value.st_uid != owner_uid
        or stat.S_IMODE(value.st_mode) & 0o022
    ):
        raise WorkerReleaseHealthError("worker_release_directory_unsafe")


def _trusted_file(
    path: Path,
    *,
    owner_uid: int,
    executable: bool,
    max_bytes: int,
) -> None:
    try:
        value = path.lstat()
    except OSError as exc:
        raise WorkerReleaseHealthError("worker_release_payload_unavailable") from exc
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_nlink != 1
        or value.st_uid != owner_uid
        or stat.S_IMODE(value.st_mode) & 0o022
        or not 0 < value.st_size <= max_bytes
        or (executable and not value.st_mode & 0o111)
    ):
        raise WorkerReleaseHealthError("worker_release_payload_unsafe")


def _validate_release_dir(release_dir: Path, *, release_root: Path, owner_uid: int) -> None:
    _trusted_directory(release_root, owner_uid=owner_uid)
    try:
        resolved_root = release_root.resolve(strict=True)
        resolved_release = release_dir.resolve(strict=True)
    except OSError as exc:
        raise WorkerReleaseHealthError("worker_release_boundary_invalid") from exc
    if resolved_release.parent != resolved_root:
        raise WorkerReleaseHealthError("worker_release_boundary_invalid")
    _trusted_directory(resolved_release, owner_uid=owner_uid)

    _trusted_file(
        resolved_release / REQUIRED_PAYLOADS[0],
        owner_uid=owner_uid,
        executable=True,
        max_bytes=16 * 1024 * 1024,
    )
    _trusted_file(
        resolved_release / REQUIRED_PAYLOADS[1],
        owner_uid=owner_uid,
        executable=False,
        max_bytes=256 * 1024,
    )


def check_pre(*, release_root: Path, current_link: Path, owner_uid: int) -> None:
    _trusted_directory(release_root, owner_uid=owner_uid)
    if not os.path.lexists(current_link):
        return
    if not current_link.is_symlink():
        raise WorkerReleaseHealthError("worker_release_current_unsafe")
    try:
        selected = current_link.resolve(strict=True)
    except OSError as exc:
        raise WorkerReleaseHealthError("worker_release_current_unsafe") from exc
    _validate_release_dir(selected, release_root=release_root, owner_uid=owner_uid)


def check_candidate(*, release_dir: Path, release_root: Path, owner_uid: int) -> None:
    _validate_release_dir(release_dir, release_root=release_root, owner_uid=owner_uid)


def check_current(
    *,
    release_dir: Path,
    release_root: Path,
    current_link: Path,
    owner_uid: int,
) -> None:
    if not current_link.is_symlink():
        raise WorkerReleaseHealthError("worker_release_current_unsafe")
    try:
        selected = current_link.resolve(strict=True)
        expected = release_dir.resolve(strict=True)
    except OSError as exc:
        raise WorkerReleaseHealthError("worker_release_current_unsafe") from exc
    if selected != expected:
        raise WorkerReleaseHealthError("worker_release_current_mismatch")
    _validate_release_dir(selected, release_root=release_root, owner_uid=owner_uid)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("pre", "candidate", "current"))
    parser.add_argument("--release-root", required=True, type=Path)
    parser.add_argument("--current-link", type=Path)
    parser.add_argument("--release-dir", type=Path)
    parser.add_argument("--agent-user", default="kolibri-agent")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        owner_uid = 0
        pwd.getpwnam(args.agent_user)
        if args.mode == "pre":
            if args.current_link is None:
                raise WorkerReleaseHealthError("worker_release_arguments_invalid")
            check_pre(
                release_root=args.release_root,
                current_link=args.current_link,
                owner_uid=owner_uid,
            )
        elif args.mode == "candidate":
            if args.release_dir is None:
                raise WorkerReleaseHealthError("worker_release_arguments_invalid")
            check_candidate(
                release_dir=args.release_dir,
                release_root=args.release_root,
                owner_uid=owner_uid,
            )
        else:
            if args.release_dir is None or args.current_link is None:
                raise WorkerReleaseHealthError("worker_release_arguments_invalid")
            check_current(
                release_dir=args.release_dir,
                release_root=args.release_root,
                current_link=args.current_link,
                owner_uid=owner_uid,
            )
    except (KeyError, WorkerReleaseHealthError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
