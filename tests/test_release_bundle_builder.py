from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest

from ops import release_bundle_builder as builder
from ops.release_controller import ReleaseManifest
from ops.release_installer import load_canonical_manifest


SOURCE_COMMIT = "0123456789abcdef"


def write(path: Path, content: str, mode: int = 0o644) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)
    return path


@pytest.fixture
def source_root(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    write(root / "backend" / "main.py", "print('kolibri')\n", 0o755)
    write(root / "backend" / "config.json", '{"mode":"production"}\n')
    write(root / "backend" / "requirements.txt", "fastapi==1.0\n")
    write(root / "backend" / "tests" / "test_runtime.py", "raise AssertionError\n")
    write(root / "backend" / "venv" / "lib" / "leak.py", "secret\n")
    write(root / "backend" / "__pycache__" / "main.pyc", "cache\n")
    write(root / "backend" / "data" / "runtime.json", '{"runtime":true}\n')
    write(root / "backend" / ".env", "DO_NOT_PACKAGE=1\n")
    write(root / "frontend" / "dist" / "index.html", "<main>Kolibri</main>\n")
    write(root / "frontend" / "dist" / "assets" / "app.js", "console.log('kolibri')\n")
    write(root / "frontend" / "node_modules" / "package" / "index.js", "dependency\n")
    write(root / "ops" / "agent_host.py", "print('agent-host')\n", 0o755)
    write(root / "ops" / "telegram.env", "DO_NOT_PACKAGE=1\n")
    return root


@pytest.fixture
def ssh_keygen() -> Path:
    path = shutil.which("ssh-keygen")
    if not path:
        pytest.skip("ssh-keygen unavailable")
    return Path(path)


@pytest.fixture
def ephemeral_signing_key(tmp_path: Path, ssh_keygen: Path) -> Path:
    key = tmp_path / "ephemeral-release-key"
    completed = subprocess.run(
        [str(ssh_keygen), "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=15,
    )
    if completed.returncode != 0:
        pytest.skip("ephemeral ssh key generation unavailable")
    key.chmod(0o600)
    return key


def make_plan(source_root: Path, output: Path) -> builder.ReleasePlan:
    return builder.plan_release(
        root=source_root,
        output=output,
        release_id="release-test-1",
        source_commit=SOURCE_COMMIT,
        artifact_uri="artifact://bundles/release-test-1.tar.gz",
        runtime_paths=("ops/agent_host.py",),
    )


def test_default_cli_is_validate_plan_and_excludes_dependencies_secrets_and_runtime_data(
    source_root: Path,
    capsys: pytest.CaptureFixture[str],
):
    output = source_root / "release" / "bundles" / "release-test-1.tar.gz"
    exit_code = builder.main(
        [
            "--root",
            str(source_root),
            "--release-id",
            "release-test-1",
            "--source-commit",
            SOURCE_COMMIT,
            "--runtime-path",
            "ops/agent_host.py",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "planned"
    assert payload["writes_performed"] is False
    assert output.exists() is False
    paths = [item["path"] for item in payload["files"]]
    assert paths == sorted(paths)
    assert paths == [
        "backend/config.json",
        "backend/main.py",
        "backend/requirements.txt",
        "frontend/dist/assets/app.js",
        "frontend/dist/index.html",
        "ops/agent_host.py",
    ]
    serialized = json.dumps(payload)
    assert "node_modules" not in serialized
    assert "__pycache__" not in serialized
    assert "telegram.env" not in serialized
    assert "runtime.json" not in serialized


def test_signed_bundle_is_deterministic_strict_and_installer_parseable(
    source_root: Path,
    ephemeral_signing_key: Path,
    ssh_keygen: Path,
    tmp_path: Path,
):
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    first_plan = make_plan(source_root, first)
    second_plan = make_plan(source_root, second)

    first_result = builder.build_release(
        first_plan,
        signing_key=ephemeral_signing_key,
        signer_identity="ephemeral-test-owner",
        ssh_keygen=ssh_keygen,
    )
    second_result = builder.build_release(
        second_plan,
        signing_key=ephemeral_signing_key,
        signer_identity="ephemeral-test-owner",
        ssh_keygen=ssh_keygen,
    )

    assert first_result["self_verified"] is True
    assert second_result["self_verified"] is True
    assert first.read_bytes() == second.read_bytes()
    assert first_result["bundle_sha256"] == hashlib.sha256(first.read_bytes()).hexdigest()
    assert stat.S_IMODE(first.stat().st_mode) == 0o644
    with tarfile.open(first, "r:gz") as archive:
        members = archive.getmembers()
        assert [item.name for item in members] == [
            ".kolibri-release/manifest.json",
            ".kolibri-release/manifest.sig",
            *[f"payload/{item.path}" for item in first_plan.files],
        ]
        assert all(item.isfile() for item in members)
        assert all(item.mtime == 0 for item in members)
        assert all(item.uid == item.gid == 0 for item in members)
        assert all(item.uname == item.gname == "" for item in members)
        manifest_bytes = archive.extractfile(".kolibri-release/manifest.json").read()
        signature_bytes = archive.extractfile(".kolibri-release/manifest.sig").read()
    assert manifest_bytes == first_plan.canonical_manifest
    assert signature_bytes.startswith(b"-----BEGIN SSH SIGNATURE-----")
    manifest_path = tmp_path / "parsed-manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    manifest_path.chmod(0o600)
    parsed = load_canonical_manifest(manifest_path)
    assert parsed.digest == first_plan.manifest_digest
    assert parsed.payload["schema_version"] == "kolibri.release.v1"
    assert parsed.payload["metadata"]["builder_contract"] == "kolibri.release-builder.v1"
    controller_manifest = ReleaseManifest.from_payload(parsed.payload)
    controller_manifest.validate()
    assert controller_manifest.digest == first_plan.manifest_digest


def test_build_and_sign_are_separate_explicit_guards_and_key_path_is_never_reported(
    source_root: Path,
    ephemeral_signing_key: Path,
    ssh_keygen: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    output = tmp_path / "guarded.tar.gz"
    common = [
        "--root",
        str(source_root),
        "--release-id",
        "release-test-1",
        "--source-commit",
        SOURCE_COMMIT,
        "--output",
        str(output),
        "--ssh-keygen",
        str(ssh_keygen),
    ]

    assert builder.main([*common, "--build"]) == 2
    error = capsys.readouterr().err
    assert "release_builder_build_requires_sign" in error
    assert str(ephemeral_signing_key) not in error
    assert output.exists() is False

    exit_code = builder.main(
        [
            *common,
            "--build",
            "--sign",
            "--signing-key",
            str(ephemeral_signing_key),
            "--signer-identity",
            "ephemeral-test-owner",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert output.is_file()
    assert str(ephemeral_signing_key) not in captured.out
    assert str(ephemeral_signing_key) not in captured.err

    original_digest = hashlib.sha256(output.read_bytes()).hexdigest()
    assert builder.main(
        [
            *common,
            "--build",
            "--sign",
            "--signing-key",
            str(ephemeral_signing_key),
            "--signer-identity",
            "ephemeral-test-owner",
        ]
    ) == 2
    assert "release_builder_output_exists" in capsys.readouterr().err
    assert hashlib.sha256(output.read_bytes()).hexdigest() == original_digest


def test_explicit_secret_runtime_path_and_symlink_fail_closed(source_root: Path, tmp_path: Path):
    with pytest.raises(builder.ReleaseBuildError, match="release_builder_runtime_path_forbidden"):
        builder.plan_release(
            root=source_root,
            output=tmp_path / "secret.tar.gz",
            release_id="release-secret",
            source_commit=SOURCE_COMMIT,
            artifact_uri="artifact://bundles/release-secret.tar.gz",
            runtime_paths=("ops/telegram.env",),
        )

    symlink = source_root / "ops" / "linked-runtime.py"
    try:
        os.symlink(source_root / "ops" / "agent_host.py", symlink)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(builder.ReleaseBuildError, match="release_builder_symlink_forbidden"):
        builder.plan_release(
            root=source_root,
            output=tmp_path / "symlink.tar.gz",
            release_id="release-symlink",
            source_commit=SOURCE_COMMIT,
            artifact_uri="artifact://bundles/release-symlink.tar.gz",
            runtime_paths=("ops/linked-runtime.py",),
        )


def test_failed_self_verification_never_publishes_partial_output(
    source_root: Path,
    ephemeral_signing_key: Path,
    ssh_keygen: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output = tmp_path / "must-not-exist.tar.gz"
    plan = make_plan(source_root, output)

    def reject(*_args, **_kwargs):
        raise builder.ReleaseBuildError("release_builder_test_verifier_rejected")

    monkeypatch.setattr(builder, "self_verify_bundle", reject)
    with pytest.raises(builder.ReleaseBuildError, match="release_builder_test_verifier_rejected"):
        builder.build_release(
            plan,
            signing_key=ephemeral_signing_key,
            signer_identity="ephemeral-test-owner",
            ssh_keygen=ssh_keygen,
        )

    assert output.exists() is False
    assert list(tmp_path.glob(".must-not-exist.tar.gz.*.tmp")) == []
