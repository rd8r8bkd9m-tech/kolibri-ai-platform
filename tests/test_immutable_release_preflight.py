from __future__ import annotations

import hashlib
import grp
import json
import os
from pathlib import Path

import pytest

from ops import immutable_release_preflight as preflight


def _release(tmp_path: Path) -> tuple[Path, Path, Path]:
    release_root = tmp_path / "releases"
    release_dir = release_root / "release-a"
    payload = release_dir / "backend/main.py"
    payload.parent.mkdir(parents=True)
    payload.write_bytes(b"app = object()\n")
    payload.chmod(0o644)
    marker = release_dir / "RELEASE_ID"
    marker.write_text("release-a\n", encoding="ascii")
    marker.chmod(0o644)
    records = []
    for relative in ("RELEASE_ID", "backend/main.py"):
        path = release_dir / relative
        records.append({
            "path": relative,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
            "mode": f"{path.stat().st_mode & 0o777:04o}",
        })
    manifest = {
        "schema_version": preflight.RELEASE_SCHEMA,
        "release_id": release_dir.name,
        "source_commit": "0123456789abcdef",
        "artifact_uri": "artifact://bundles/release-a.tar.gz",
        "compatibility_epoch": "kolibri-os-v1",
        "files": records,
        "metadata": {},
    }
    metadata = release_dir / ".kolibri-release"
    metadata.mkdir()
    (metadata / "manifest.json").write_bytes(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    )
    (metadata / "manifest.sig").write_text("signed-test-evidence\n", encoding="ascii")
    current = tmp_path / "current"
    current.symlink_to(release_dir)
    return release_root, release_dir, current


def test_exact_manifest_file_set_passes_without_mutation(tmp_path):
    release_root, release_dir, current = _release(tmp_path)
    before = sorted(path.relative_to(release_dir) for path in release_dir.rglob("*"))

    result = preflight.inspect_current(current=current, release_root=release_root)

    assert result["status"] == "passed"
    assert result["mutation"] == "none"
    assert result["extra_file_total"] == 0
    assert result["missing_file_total"] == 0
    assert sorted(path.relative_to(release_dir) for path in release_dir.rglob("*")) == before


def test_unmanifested_bytecode_blocks_apply_with_bounded_repair_plan(tmp_path):
    release_root, release_dir, current = _release(tmp_path)
    cache = release_dir / "backend/__pycache__/main.cpython-312.pyc"
    cache.parent.mkdir()
    cache.write_bytes(b"runtime cache")

    result = preflight.inspect_current(current=current, release_root=release_root)

    assert result["status"] == "blocked"
    assert result["reason"] == "immutable_release_file_set_polluted"
    assert result["extra_file_total"] == 1
    assert result["reported_extra_paths"] == [
        "backend/__pycache__/main.cpython-312.pyc",
    ]
    assert result["repair_plan"] == list(preflight.REPAIR_PLAN)
    assert cache.read_bytes() == b"runtime cache"


def test_manifested_digest_drift_is_not_misclassified_as_cache_pollution(tmp_path):
    release_root, release_dir, current = _release(tmp_path)
    (release_dir / "backend/main.py").write_bytes(b"changed\n")

    result = preflight.inspect_current(current=current, release_root=release_root)

    assert result["status"] == "blocked"
    assert result["reason"] == "immutable_release_integrity_mismatch"
    assert result["integrity_error_total"] >= 1
    assert any(
        item["path"] == "backend/main.py" and item["reason"] in {"size", "sha256"}
        for item in result["reported_integrity_errors"]
    )


def test_cli_returns_nonzero_for_pollution_and_never_repairs_it(tmp_path, capsys):
    release_root, release_dir, current = _release(tmp_path)
    extra = release_dir / "ops/__pycache__/control_plane_endpoint.pyc"
    extra.parent.mkdir(parents=True)
    extra.write_bytes(b"cache")
    token = tmp_path / "owner-api-token"
    token.write_text("opaque-test-token\n", encoding="utf-8")
    token.chmod(0o640)
    group_name = grp.getgrgid(os.getegid()).gr_name

    return_code = preflight.main([
        "--current",
        str(current),
        "--release-root",
        str(release_root),
        "--owner-token",
        str(token),
        "--owner-token-group",
        group_name,
    ])
    output = json.loads(capsys.readouterr().out)

    assert return_code == 2
    assert output["status"] == "blocked"
    assert output["mutation"] == "none"
    assert extra.is_file()


def test_owner_token_preflight_checks_only_metadata_and_rejects_symlink(tmp_path):
    token = tmp_path / "owner-api-token"
    token.write_text("value-never-returned\n", encoding="utf-8")
    token.chmod(0o640)

    result = preflight.inspect_owner_token_metadata(
        token,
        expected_uid=os.geteuid(),
        expected_gid=os.getegid(),
    )

    assert result["owner_token_file"] == "metadata_verified_without_secret_read"
    assert "value-never-returned" not in json.dumps(result)

    real = tmp_path / "real-token"
    token.rename(real)
    token.symlink_to(real)
    try:
        with pytest.raises(
            preflight.ImmutableReleasePreflightError,
            match="owner_api_token_file_permissions_invalid",
        ):
            preflight.inspect_owner_token_metadata(
                token,
                expected_uid=os.geteuid(),
                expected_gid=os.getegid(),
            )
    finally:
        token.unlink(missing_ok=True)
