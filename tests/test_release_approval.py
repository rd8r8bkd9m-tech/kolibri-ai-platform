import importlib.util
import json
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_release_approval():
    path = ROOT / "ops" / "release_approval.py"
    spec = importlib.util.spec_from_file_location("release_approval_contract", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ssh_keygen() -> Path:
    path = shutil.which("ssh-keygen")
    if not path:
        pytest.skip("ssh-keygen unavailable")
    return Path(path)


@pytest.fixture
def signing_material(tmp_path: Path, ssh_keygen: Path):
    key = tmp_path / "owner-release-key"
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
    public = subprocess.run(
        [str(ssh_keygen), "-y", "-f", str(key)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=15,
    ).stdout.strip()
    allowed = tmp_path / "allowed_signers"
    allowed.write_bytes(b"owner " + public + b"\n")
    allowed.chmod(0o600)
    return key, allowed


def make_release_files(tmp_path, ssh_keygen, key, release_id, commit):
    from ops.release_controller import ReleaseFile, ReleaseManifest

    manifest = ReleaseManifest(
        release_id=release_id,
        source_commit=commit,
        artifact_uri=f"artifact://bundles/{release_id}.tar.gz",
        files=(ReleaseFile("backend/main.py", "a" * 64, 42),),
    )
    manifest_path = tmp_path / f"{release_id}.manifest.json"
    manifest_path.write_bytes(manifest.canonical_bytes())
    manifest_path.chmod(0o600)
    completed = subprocess.run(
        [
            str(ssh_keygen),
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            "kolibri-release",
            str(manifest_path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=15,
    )
    assert completed.returncode == 0
    signature_path = Path(f"{manifest_path}.sig")
    signature_path.chmod(0o600)
    return manifest, manifest_path, signature_path


def binding_args(tmp_path, ssh_keygen, key, allowed):
    current, current_manifest, current_signature = make_release_files(
        tmp_path,
        ssh_keygen,
        key,
        "kolibri-2026.07.11-rc1",
        "1" * 40,
    )
    rollback, rollback_manifest, rollback_signature = make_release_files(
        tmp_path,
        ssh_keygen,
        key,
        "kolibri-2026.07.10-known-good",
        "2" * 40,
    )
    rollout = tmp_path / "home-rollout.json"
    rollout.write_text(
        json.dumps({
            "schema_version": current.schema_version,
            "release_id": current.release_id,
            "manifest_digest": current.digest,
            "transport": "control-plane-api-only",
            "waves": [{"name": "home-canary", "nodes": ["home"]}],
        }),
        encoding="utf-8",
    )
    rollout.chmod(0o600)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    return [
        "--manifest", str(current_manifest),
        "--signature", str(current_signature),
        "--rollback-manifest", str(rollback_manifest),
        "--rollback-signature", str(rollback_signature),
        "--allowed-signers", str(allowed),
        "--release-signer-identity", "owner",
        "--rollout-plan", str(rollout),
        "--approval-id", "approval-home-rc1",
        "--expires-at", expires,
        "--nonce", "approval-home-rc1-nonce",
        "--owner-signer-identity", "owner",
    ], current, rollback, rollout


def test_plan_is_read_only_and_sign_writes_private_atomic_approval(
    tmp_path, ssh_keygen, signing_material, capsys
):
    approval = load_release_approval()
    key, allowed = signing_material
    args, current, rollback, _rollout = binding_args(tmp_path, ssh_keygen, key, allowed)
    output = tmp_path / "approvals" / "home-rc1.json"

    assert approval.main(["plan", *args]) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["status"] == "planned"
    assert planned["writes_performed"] is False
    assert planned["rollout_plan"] == [{"name": "home-canary", "nodes": ["home"]}]
    assert output.exists() is False

    assert approval.main([
        "sign",
        *args,
        "--owner-signing-key", str(key),
        "--output", str(output),
        "--ssh-keygen", str(ssh_keygen),
    ]) == 0
    captured = capsys.readouterr()
    signed = json.loads(captured.out)
    assert signed["status"] == "signed"
    assert signed["release_id"] == current.release_id
    assert signed["rollback_release_id"] == rollback.release_id
    assert str(key) not in captured.out
    assert str(key) not in captured.err
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    body = json.loads(output.read_text(encoding="utf-8"))
    assert body["signature"].startswith("-----BEGIN SSH SIGNATURE-----")
    verified = approval.verify_signed_approval(
        body,
        allowed_signers=allowed,
        ssh_keygen=ssh_keygen,
    )
    assert verified["approval_id"] == "approval-home-rc1"


def test_submit_reverifies_signature_and_targets_only_home_control_plane(
    tmp_path, ssh_keygen, signing_material, capsys, monkeypatch
):
    approval = load_release_approval()
    key, allowed = signing_material
    args, current, _rollback, _rollout = binding_args(tmp_path, ssh_keygen, key, allowed)
    output = tmp_path / "approval.json"
    assert approval.main([
        "sign",
        *args,
        "--owner-signing-key", str(key),
        "--output", str(output),
        "--ssh-keygen", str(ssh_keygen),
    ]) == 0
    capsys.readouterr()

    class FakeClient:
        def __init__(self):
            self.calls = []

        def request(self, method, path, body):
            self.calls.append((method, path, body))
            return {
                "status": "approved",
                "approval_id": body["approval_id"],
                "release_id": body["release_id"],
            }

    fake = FakeClient()
    monkeypatch.setattr(
        approval.ControlPlaneClient,
        "from_environment",
        lambda timeout=10.0, control_url=None: fake,
    )
    assert approval.main([
        "submit",
        "--approval-file", str(output),
        "--allowed-signers", str(allowed),
        "--ssh-keygen", str(ssh_keygen),
        "--control-url", "http://10.99.0.1:9101",
    ]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result == {
        "approval_id": "approval-home-rc1",
        "control_plane": "home",
        "release_id": current.release_id,
        "schema_version": approval.CLI_SCHEMA,
        "status": "submitted",
        "writes_performed": True,
    }
    assert [(method, path) for method, path, _body in fake.calls] == [
        ("POST", "/v1/approvals")
    ]


def test_rollout_plan_digest_mismatch_fails_before_owner_key_access(
    tmp_path, ssh_keygen, signing_material, capsys
):
    approval = load_release_approval()
    key, allowed = signing_material
    args, _current, _rollback, rollout = binding_args(tmp_path, ssh_keygen, key, allowed)
    value = json.loads(rollout.read_text(encoding="utf-8"))
    value["manifest_digest"] = "sha256:" + "f" * 64
    rollout.write_text(json.dumps(value), encoding="utf-8")
    missing_key = tmp_path / "must-not-be-read"

    assert approval.main([
        "sign",
        *args,
        "--owner-signing-key", str(missing_key),
        "--output", str(tmp_path / "approval.json"),
        "--ssh-keygen", str(ssh_keygen),
    ]) == 2
    captured = capsys.readouterr()
    error = json.loads(captured.err)
    assert error["error_type"] == "release_approval_rollout_plan_binding_mismatch"
    assert str(missing_key) not in captured.err


def test_sign_rejects_unsafe_key_permissions_and_unsafe_output_parent(
    tmp_path, ssh_keygen, signing_material, capsys
):
    approval = load_release_approval()
    key, allowed = signing_material
    args, _current, _rollback, _rollout = binding_args(tmp_path, ssh_keygen, key, allowed)
    key.chmod(0o644)

    assert approval.main([
        "sign",
        *args,
        "--owner-signing-key", str(key),
        "--output", str(tmp_path / "approval.json"),
        "--ssh-keygen", str(ssh_keygen),
    ]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.err)["error_type"] == (
        "release_approval_signing_key_permissions_invalid"
    )
    assert str(key) not in captured.err

    key.chmod(0o600)
    unsafe_parent = tmp_path / "unsafe-output"
    unsafe_parent.mkdir(mode=0o700)
    unsafe_parent.chmod(0o777)
    output = unsafe_parent / "approval.json"
    assert approval.main([
        "sign",
        *args,
        "--owner-signing-key", str(key),
        "--output", str(output),
        "--ssh-keygen", str(ssh_keygen),
    ]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.err)["error_type"] == "release_approval_output_invalid"
    assert output.exists() is False
    assert str(key) not in captured.err
