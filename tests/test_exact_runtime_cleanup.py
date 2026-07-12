from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from ops import exact_runtime_cleanup as cleanup


def test_cleanup_is_dry_run_and_requires_digest_bound_apply(tmp_path: Path) -> None:
    payload = b"identified-runtime-pollutant"
    digest = hashlib.sha256(payload).hexdigest()
    first = tmp_path / "one" / "libopentui.so"
    second = tmp_path / "two" / "libopentui.so"
    for path in (first, second):
        path.parent.mkdir()
        path.write_bytes(payload)

    plan = cleanup.scan(
        tmp_path,
        uid=os.geteuid(),
        size=len(payload),
        sha256=digest,
    )

    assert plan["mutation"] == "none"
    assert plan["candidate_count"] == 2
    assert first.exists() and second.exists()
    with pytest.raises(cleanup.CleanupError, match="ack_mismatch"):
        cleanup.apply(plan, ack_digest="0" * 64)

    result = cleanup.apply(plan, ack_digest=plan["scan_digest"])
    assert result["status"] == "completed"
    assert result["removed_count"] == 2
    assert not first.exists() and not second.exists()


def test_cleanup_rejects_symlink_hardlink_and_changed_inode(tmp_path: Path) -> None:
    payload = b"same-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    source = tmp_path / "source.bin"
    source.write_bytes(payload)
    symlink = tmp_path / "symlink" / "libopentui.so"
    symlink.parent.mkdir()
    symlink.symlink_to(source)
    hardlink = tmp_path / "hardlink" / "libopentui.so"
    hardlink.parent.mkdir()
    os.link(source, hardlink)
    exact = tmp_path / "exact" / "libopentui.so"
    exact.parent.mkdir()
    exact.write_bytes(payload)

    plan = cleanup.scan(
        tmp_path,
        uid=os.geteuid(),
        size=len(payload),
        sha256=digest,
    )
    assert [Path(item["path"]) for item in plan["candidates"]] == [exact]

    exact.unlink()
    exact.write_bytes(payload)
    result = cleanup.apply(plan, ack_digest=plan["scan_digest"])
    assert result["status"] == "partial"
    assert result["removed_count"] == 0
    assert result["skipped_count"] == 1
    assert exact.exists()
