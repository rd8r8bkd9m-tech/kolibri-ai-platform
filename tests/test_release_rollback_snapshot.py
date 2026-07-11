from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from ops import release_bundle_builder as bundle_builder
from ops import home_control_plane_release
from ops import release_rollback_snapshot as snapshot


SOURCE_COMMIT = "0123456789abcdef"
SIGNER_IDENTITY = "rollback-test-owner"
RUNBOOK = Path(__file__).resolve().parents[1] / "docs" / "FIRST_HOME_ROLLBACK_SNAPSHOT.md"


def write(path: Path, value: bytes, mode: int = 0o644) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    path.chmod(mode)
    return path


@pytest.fixture
def ssh_keygen() -> Path:
    value = shutil.which("ssh-keygen")
    if not value:
        pytest.skip("ssh-keygen unavailable")
    return Path(value)


@pytest.fixture
def signing_key(tmp_path: Path, ssh_keygen: Path) -> Path:
    key = tmp_path / "release-signing-key"
    completed = subprocess.run(
        [str(ssh_keygen), "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=15,
    )
    if completed.returncode != 0:
        pytest.skip("ephemeral SSH key unavailable")
    key.chmod(0o600)
    return key


@pytest.fixture
def signed_product_release(
    tmp_path: Path,
    signing_key: Path,
    ssh_keygen: Path,
) -> tuple[Path, Path]:
    source = tmp_path / "product-source"
    release_id = "current-product-1"
    write(source / "backend" / "main.py", b"print('known-good')\n", 0o755)
    write(source / "backend" / "settings.json", b'{"known_good":true}\n')
    write(source / "frontend" / "dist" / "index.html", b"<main>known-good</main>\n")
    write(source / "frontend" / "dist" / "assets" / "app.js", b"knownGood();\n")
    write(source / "ops" / "control_plane_endpoint.py", b"HOME_ONLY = True\n", 0o755)
    write(source / "RELEASE_ID", f"{release_id}\n".encode("ascii"))

    bundle = tmp_path / f"{release_id}.tar.gz"
    plan = bundle_builder.plan_release(
        root=source,
        output=bundle,
        release_id=release_id,
        source_commit=SOURCE_COMMIT,
        artifact_uri=f"artifact://bundles/{release_id}.tar.gz",
        runtime_paths=("RELEASE_ID", "ops/control_plane_endpoint.py"),
    )
    result = bundle_builder.build_release(
        plan,
        signing_key=signing_key,
        signer_identity=SIGNER_IDENTITY,
        ssh_keygen=ssh_keygen,
    )
    assert result["self_verified"] is True

    current = tmp_path / release_id
    current.mkdir()
    with tarfile.open(bundle, "r:gz") as archive:
        for member in archive.getmembers():
            if member.name.startswith("payload/"):
                relative = member.name.removeprefix("payload/")
            elif member.name in {
                ".kolibri-release/manifest.json",
                ".kolibri-release/manifest.sig",
            }:
                relative = member.name
            else:
                continue
            stream = archive.extractfile(member)
            assert stream is not None
            write(current / relative, stream.read(), member.mode)

    public_parts = signing_key.with_suffix(".pub").read_text(encoding="utf-8").split()
    allowed_signers = tmp_path / "allowed_signers"
    write(
        allowed_signers,
        f"{SIGNER_IDENTITY} {public_parts[0]} {public_parts[1]}\n".encode("ascii"),
        0o600,
    )
    return current, allowed_signers


def runtime_sources(tmp_path: Path) -> tuple[dict[str, Path], Path, str]:
    active_root = tmp_path / "active-split-runtime"
    mappings: dict[str, Path] = {}
    for destination in snapshot.EFFECTIVE_RUNTIME_PATHS:
        source = write(
            active_root / destination,
            f"# exact active bytes: {destination}\n".encode("utf-8"),
            0o755 if destination.endswith(".py") else 0o644,
        )
        mappings[destination] = source.resolve()
    sentinel = write(
        tmp_path / "committed-source" / snapshot.MIMO_RESPONSE_AGENT_PROFILE_PATH,
        b"# required response-only profile\n",
    ).resolve()
    return mappings, sentinel, hashlib.sha256(sentinel.read_bytes()).hexdigest()


def make_plan(
    tmp_path: Path,
    signed_product_release: tuple[Path, Path],
    ssh_keygen: Path,
) -> snapshot.SnapshotPlan:
    current, allowed_signers = signed_product_release
    mappings, sentinel, sentinel_sha256 = runtime_sources(tmp_path)
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)
    return snapshot.plan_snapshot(
        current_root=current,
        snapshot_root=output_parent / "rollback-snapshot",
        rollback_release_id="rollback-current-product-1-capture",
        allowed_signers=allowed_signers,
        signer_identity=SIGNER_IDENTITY,
        ssh_keygen=ssh_keygen,
        runtime_maps=mappings,
        mimo_sentinel_source=sentinel,
        mimo_sentinel_commit=SOURCE_COMMIT,
        mimo_sentinel_sha256=sentinel_sha256,
    )


def test_pollution_requires_digest_ack_and_is_never_copied(
    tmp_path: Path,
    signed_product_release: tuple[Path, Path],
    ssh_keygen: Path,
) -> None:
    current, _allowed_signers = signed_product_release
    write(current / "backend" / "__pycache__" / "main.cpython.pyc", b"unbound cache\n")
    write(current / "frontend" / "dist" / "unbound-debug.log", b"unbound log\n")

    plan = make_plan(tmp_path, signed_product_release, ssh_keygen)

    assert plan.blocked is True
    assert plan.unbound_digest.startswith("sha256:")
    assert {item.path for item in plan.unbound_entries} >= {
        "backend/__pycache__",
        "backend/__pycache__/main.cpython.pyc",
        "frontend/dist/unbound-debug.log",
    }
    with pytest.raises(
        snapshot.RollbackSnapshotError,
        match="rollback_snapshot_unbound_ack_required",
    ):
        snapshot.capture_snapshot(plan, acknowledge_unbound_digest=None)

    result = snapshot.capture_snapshot(
        plan,
        acknowledge_unbound_digest=plan.unbound_digest,
    )
    output = plan.snapshot_root

    assert result["status"] == "captured"
    assert (output / "RELEASE_ID").read_text(encoding="ascii") == (
        "rollback-current-product-1-capture\n"
    )
    assert not (output / "backend" / "__pycache__").exists()
    assert not (output / "frontend" / "dist" / "unbound-debug.log").exists()
    provenance = json.loads((output / snapshot.PROVENANCE_NAME).read_text(encoding="utf-8"))
    assert provenance["source_release"]["release_id"] == "current-product-1"
    assert provenance["rollback_release_id"] == "rollback-current-product-1-capture"
    assert provenance["excluded_unbound_entries"]["digest"] == plan.unbound_digest
    assert provenance["excluded_unbound_entries"]["contents_read"] is False
    assert provenance["mimo_profile_disclosure"]["effective_at_capture"] is False
    assert "not evidence" in provenance["mimo_profile_disclosure"]["statement"]
    assert snapshot.verify_snapshot(output)["status"] == "verified"

    bundle_plan = bundle_builder.plan_release(
        root=output,
        output=tmp_path / "rollback-plan.tar.gz",
        release_id=plan.rollback_release_id,
        source_commit=SOURCE_COMMIT,
        artifact_uri=f"artifact://bundles/{plan.rollback_release_id}.tar.gz",
        runtime_paths=("RELEASE_ID", snapshot.PROVENANCE_NAME, *snapshot.SPLIT_RUNTIME_PATHS),
    )
    bundle_paths = {item.path: item for item in bundle_plan.files}
    assert not any("__pycache__" in path for path in bundle_paths)
    assert bundle_paths["RELEASE_ID"].sha256 == hashlib.sha256(
        f"{plan.rollback_release_id}\n".encode("ascii")
    ).hexdigest()
    assert set(snapshot.SPLIT_RUNTIME_PATHS).issubset(bundle_paths)
    assert snapshot.PROVENANCE_NAME in bundle_paths


def test_manifest_bound_product_tamper_and_wrong_sentinel_digest_fail_closed(
    tmp_path: Path,
    signed_product_release: tuple[Path, Path],
    ssh_keygen: Path,
) -> None:
    current, allowed_signers = signed_product_release
    mappings, sentinel, sentinel_sha256 = runtime_sources(tmp_path)
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)

    with pytest.raises(
        snapshot.RollbackSnapshotError,
        match="rollback_snapshot_bound_file_digest_mismatch",
    ):
        snapshot.plan_snapshot(
            current_root=current,
            snapshot_root=output_parent / "wrong-sentinel",
            rollback_release_id="rollback-wrong-sentinel",
            allowed_signers=allowed_signers,
            signer_identity=SIGNER_IDENTITY,
            ssh_keygen=ssh_keygen,
            runtime_maps=mappings,
            mimo_sentinel_source=sentinel,
            mimo_sentinel_commit=SOURCE_COMMIT,
            mimo_sentinel_sha256="0" * 64,
        )

    write(current / "backend" / "main.py", b"tampered after signing\n", 0o755)
    with pytest.raises(
        snapshot.RollbackSnapshotError,
        match="rollback_snapshot_bound_file_(?:size|digest)_mismatch",
    ):
        snapshot.plan_snapshot(
            current_root=current,
            snapshot_root=output_parent / "tampered-product",
            rollback_release_id="rollback-tampered-product",
            allowed_signers=allowed_signers,
            signer_identity=SIGNER_IDENTITY,
            ssh_keygen=ssh_keygen,
            runtime_maps=mappings,
            mimo_sentinel_source=sentinel,
            mimo_sentinel_commit=SOURCE_COMMIT,
            mimo_sentinel_sha256=sentinel_sha256,
        )


def test_snapshot_verifier_rejects_post_capture_extra_file(
    tmp_path: Path,
    signed_product_release: tuple[Path, Path],
    ssh_keygen: Path,
) -> None:
    plan = make_plan(tmp_path, signed_product_release, ssh_keygen)
    snapshot.capture_snapshot(plan, acknowledge_unbound_digest=None)
    write(plan.snapshot_root / "ops" / "__pycache__" / "injected.pyc", b"late extra\n")

    with pytest.raises(
        snapshot.RollbackSnapshotError,
        match="rollback_snapshot_output_file_set_mismatch",
    ):
        snapshot.verify_snapshot(plan.snapshot_root)


def test_snapshot_verifier_rejects_erased_mimo_sentinel_disclosure(
    tmp_path: Path,
    signed_product_release: tuple[Path, Path],
    ssh_keygen: Path,
) -> None:
    plan = make_plan(tmp_path, signed_product_release, ssh_keygen)
    snapshot.capture_snapshot(plan, acknowledge_unbound_digest=None)
    provenance_path = plan.snapshot_root / snapshot.PROVENANCE_NAME
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["mimo_profile_disclosure"]["effective_at_capture"] = True
    provenance_path.write_bytes(snapshot._canonical_json(provenance))

    with pytest.raises(
        snapshot.RollbackSnapshotError,
        match="rollback_snapshot_provenance_invalid",
    ):
        snapshot.verify_snapshot(plan.snapshot_root)


def test_runtime_map_requires_every_effective_split_path(tmp_path: Path) -> None:
    assert set(snapshot.SPLIT_RUNTIME_PATHS) == (
        set(home_control_plane_release.REQUIRED_RUNTIME_PATHS) - {"RELEASE_ID"}
    )
    with pytest.raises(
        snapshot.RollbackSnapshotError,
        match="rollback_snapshot_runtime_map_incomplete",
    ):
        snapshot._parse_runtime_maps(
            [f"{snapshot.EFFECTIVE_RUNTIME_PATHS[0]}={tmp_path / 'one.py'}"]
        )


def test_runbook_binds_new_rollback_id_and_provenance_to_full_profile() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")

    assert 'ROLLBACK_ID="rollback-${SOURCE_RELEASE_ID}-${STAMP}"' in text
    assert '--rollback-release-id "$ROLLBACK_ID"' in text
    assert "--acknowledge-unbound-digest \"$UNBOUND_DIGEST\"" in text
    assert "--runtime-path ROLLBACK_PROVENANCE.json" in text
    assert "--runtime-path ops/mimo/kolibri-response-only.md" in text
    assert "--release-id \"$ROLLBACK_ID\"" in text
    assert "--release-id \"$SOURCE_RELEASE_ID\"" not in text
    assert "--exclude='*/__pycache__'" not in text
