import hashlib
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from ops import release_bundle_builder as builder


ROOT = Path(__file__).resolve().parents[1]


def load_stager():
    path = ROOT / "ops" / "home_release_artifact_stager.py"
    spec = importlib.util.spec_from_file_location("home_release_artifact_stager_contract", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def signed_bundle(tmp_path):
    ssh_keygen = shutil.which("ssh-keygen")
    if not ssh_keygen:
        pytest.skip("ssh-keygen unavailable")
    key_dir = tmp_path / "keys"
    key_dir.mkdir(mode=0o700)
    key = key_dir / "release-owner"
    completed = subprocess.run(
        [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=15,
    )
    if completed.returncode != 0:
        pytest.skip("ephemeral ssh key generation unavailable")
    key.chmod(0o600)

    source = tmp_path / "source"
    (source / "backend").mkdir(parents=True)
    (source / "backend" / "main.py").write_text("print('kolibri')\n", encoding="utf-8")
    (source / "frontend" / "dist").mkdir(parents=True)
    (source / "frontend" / "dist" / "index.html").write_text(
        "<main>Kolibri</main>\n", encoding="utf-8"
    )
    bundle = tmp_path / "kolibri-home-rc1.tar.gz"
    plan = builder.plan_release(
        root=source,
        output=bundle,
        release_id="kolibri-home-rc1",
        source_commit="1" * 40,
        artifact_uri="artifact://bundles/kolibri-home-rc1.tar.gz",
    )
    builder.build_release(
        plan,
        signing_key=key,
        signer_identity="owner",
        ssh_keygen=Path(ssh_keygen),
    )
    bundle.chmod(0o600)
    return bundle, plan


def test_inspect_binds_canonical_manifest_and_stage_is_immutable_and_idempotent(
    tmp_path, signed_bundle
):
    stager = load_stager()
    bundle, plan = signed_bundle
    inspected = stager.inspect_bundle(bundle)
    expected_digest = hashlib.sha256(bundle.read_bytes()).hexdigest()

    assert inspected.release_id == "kolibri-home-rc1"
    assert inspected.artifact_relative == "bundles/kolibri-home-rc1.tar.gz"
    assert inspected.manifest_digest == plan.manifest_digest
    assert inspected.bundle_sha256 == expected_digest

    root = tmp_path / "artifacts"
    root.mkdir(mode=0o700)
    planned = stager.stage_artifact(
        source=None,
        artifact_relative=inspected.artifact_relative,
        expected_sha256=inspected.bundle_sha256,
        expected_size=inspected.size_bytes,
        root=root,
        apply=False,
    )
    assert planned["status"] == "planned"
    assert planned["writes_performed"] is False

    staged = stager.stage_artifact(
        source=bundle,
        artifact_relative=inspected.artifact_relative,
        expected_sha256=inspected.bundle_sha256,
        expected_size=inspected.size_bytes,
        root=root,
        apply=True,
    )
    destination = root / inspected.artifact_relative
    assert staged["status"] == "staged"
    assert destination.read_bytes() == bundle.read_bytes()
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600

    replay = stager.stage_artifact(
        source=bundle,
        artifact_relative=inspected.artifact_relative,
        expected_sha256=inspected.bundle_sha256,
        expected_size=inspected.size_bytes,
        root=root,
        apply=True,
    )
    assert replay["status"] == "already_staged"
    assert replay["writes_performed"] is False


def test_stage_rejects_collision_symlink_and_non_bundle_namespace(tmp_path, signed_bundle):
    stager = load_stager()
    bundle, _plan = signed_bundle
    inspected = stager.inspect_bundle(bundle)
    root = tmp_path / "artifacts"
    root.mkdir(mode=0o700)
    (root / "bundles").mkdir(mode=0o700)
    collision = root / inspected.artifact_relative
    collision.write_bytes(b"different")
    collision.chmod(0o600)

    with pytest.raises(stager.ArtifactStageError, match="artifact_collision"):
        stager.stage_artifact(
            source=None,
            artifact_relative=inspected.artifact_relative,
            expected_sha256=inspected.bundle_sha256,
            expected_size=inspected.size_bytes,
            root=root,
            apply=False,
        )
    with pytest.raises(stager.ArtifactStageError, match="artifact_relative_invalid"):
        stager.stage_artifact(
            source=None,
            artifact_relative="other/kolibri.tar.gz",
            expected_sha256=inspected.bundle_sha256,
            expected_size=inspected.size_bytes,
            root=root,
            apply=False,
        )

    linked = tmp_path / "linked-bundle"
    try:
        os.symlink(bundle, linked)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(stager.ArtifactStageError, match="source_invalid"):
        stager.stage_artifact(
            source=linked,
            artifact_relative="bundles/other.tar.gz",
            expected_sha256=inspected.bundle_sha256,
            expected_size=inspected.size_bytes,
            root=root,
            apply=True,
        )


def test_wrapper_is_dry_run_by_default_and_has_no_embedded_home_address():
    script = (ROOT / "scripts" / "stage-home-release-bundle.sh").read_text(encoding="utf-8")
    assert "APPLY=false" in script
    assert "--apply" in script
    assert "control_plane_endpoint.py" in script
    assert "PYTHONPATH=/usr/local/lib/kolibri" in script
    assert 'SCP_OPTIONS=(-O "${SSH_OPTIONS[@]}")' in script
    assert "10.99.0.1" not in script
    assert "release_bundle_apply" not in script
