from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "release_snapshot_marker.py"
RUNBOOK = ROOT / "docs" / "SIGNED_HOME_RELEASE_CANARY.md"


def load_marker_module():
    spec = importlib.util.spec_from_file_location("release_snapshot_marker", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_marker_is_created_once_with_exact_safe_payload(tmp_path: Path) -> None:
    marker = load_marker_module()
    created = marker.create_release_marker(tmp_path, "kolibri-release-1")

    assert created == tmp_path / "RELEASE_ID"
    assert created.read_bytes() == b"kolibri-release-1\n"
    assert stat.S_IMODE(created.stat().st_mode) == 0o644
    with pytest.raises(marker.SnapshotMarkerError, match="release_snapshot_marker_exists"):
        marker.create_release_marker(tmp_path, "kolibri-release-1")


def test_marker_refuses_git_worktree_invalid_id_and_symlink_root(tmp_path: Path) -> None:
    marker = load_marker_module()
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    with pytest.raises(marker.SnapshotMarkerError, match="release_snapshot_git_worktree_forbidden"):
        marker.create_release_marker(worktree, "kolibri-release-1")

    isolated = tmp_path / "isolated"
    isolated.mkdir()
    with pytest.raises(marker.SnapshotMarkerError, match="release_snapshot_id_invalid"):
        marker.create_release_marker(isolated, "../unsafe")

    linked = tmp_path / "linked"
    linked.symlink_to(isolated, target_is_directory=True)
    with pytest.raises(marker.SnapshotMarkerError, match="release_snapshot_root_invalid"):
        marker.create_release_marker(linked, "kolibri-release-1")


def test_cli_emits_only_sanitized_marker_evidence(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--release-id", "release-2"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == {
        "marker": "RELEASE_ID",
        "release_id": "release-2",
        "schema_version": "kolibri.release-snapshot-marker.v1",
        "status": "created",
    }


def test_signed_home_runbook_uses_isolated_markers_for_both_bundles() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")

    assert '-cf - backend frontend/dist ops/control_plane_endpoint.py \\\n' in text
    assert "ops/control_plane_endpoint.py RELEASE_ID" not in text
    assert text.count("python3 ops/release_snapshot_marker.py") == 2
    assert text.count("--runtime-path RELEASE_ID") == 2
    assert 'git archive --format=tar "$SOURCE_COMMIT"' in text
    assert '--root "$SOURCE_ROOT"' in text
    assert '--root "$WORKTREE"' not in text
