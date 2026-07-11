from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def release_module():
    return load_module("release_installer_contract", ROOT / "ops" / "release_installer.py")


def write_executable(path: Path, body: str) -> Path:
    path.write_text(f"#!{sys.executable}\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def write_policy(release, path: Path, health_script: Path, *, services=None, defaults=None):
    payload = {
        "schema_version": release.RELEASE_POLICY_SCHEMA,
        "services": services or [],
        "default_services": defaults or [],
        "pre_health": [{"name": "baseline", "argv": [str(health_script)], "timeout_seconds": 5}],
        "post_health": [{"name": "activated", "argv": [str(health_script)], "timeout_seconds": 5}],
        "service_timeout_seconds": 5,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def make_installer(release, tmp_path: Path, *, fail_on_release: str = ""):
    artifact_root = tmp_path / "artifacts"
    release_root = tmp_path / "opt" / "kolibri-ai" / "releases"
    current_link = tmp_path / "opt" / "kolibri-ai" / "current"
    artifact_root.mkdir(parents=True)
    release_root.mkdir(parents=True)
    allowed_signers = tmp_path / "release_allowed_signers"
    allowed_signers.write_text("owner ssh-ed25519 public-material\n", encoding="utf-8")
    owner_allowed_signers = tmp_path / "owner_allowed_signers"
    owner_allowed_signers.write_text("owner ssh-ed25519 public-material\n", encoding="utf-8")
    health_script = write_executable(
        tmp_path / "release-health",
        "from pathlib import Path\n"
        f"current = Path({str(current_link)!r})\n"
        "target = current.resolve().name if current.is_symlink() else ''\n"
        f"raise SystemExit(1 if {bool(fail_on_release)!r} and target == {fail_on_release!r} else 0)",
    )
    policy_path = tmp_path / "release-policy.json"
    write_policy(release, policy_path, health_script)
    ssh_keygen = Path(shutil.which("ssh-keygen") or "/usr/bin/ssh-keygen")
    config = release.ReleaseInstallerConfig(
        artifact_root=artifact_root,
        release_root=release_root,
        current_link=current_link,
        allowed_signers=allowed_signers,
        policy_path=policy_path,
        ssh_keygen=ssh_keygen,
        systemctl=Path("/usr/bin/false"),
        owner_allowed_signers=owner_allowed_signers,
        max_bundle_bytes=4 * 1024 * 1024,
        max_unpacked_bytes=16 * 1024 * 1024,
        max_members=100,
        download_timeout_seconds=5,
    )
    return release.ReleaseInstaller(config), health_script


def canonical_manifest(release, release_id: str, artifact_uri: str, files: dict[str, tuple[bytes, int]]):
    records = [
        {
            "path": path,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "mode": f"{mode:04o}",
        }
        for path, (content, mode) in sorted(files.items())
    ]
    payload = {
        "schema_version": release.RELEASE_SCHEMA,
        "release_id": release_id,
        "source_commit": "0123456789abcdef",
        "artifact_uri": artifact_uri,
        "compatibility_epoch": "kolibri-os-v1",
        "files": records,
        "metadata": {"contract": "release-installer-test"},
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return payload, f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def add_bytes(archive: tarfile.TarFile, name: str, content: bytes, mode: int = 0o644):
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mode = mode
    archive.addfile(info, io.BytesIO(content))


def build_bundle(
    release,
    bundle: Path,
    release_id: str,
    artifact_uri: str,
    *,
    files: dict[str, tuple[bytes, int]] | None = None,
    manifest_mutator=None,
    unsafe_member: tarfile.TarInfo | None = None,
    signature_bytes: bytes = b"detached-sshsig",
    canonical_manifest_bytes: bool = True,
):
    files = files or {"bin/kolibri-app": (b"release-bytes", 0o755)}
    manifest, digest = canonical_manifest(release, release_id, artifact_uri, files)
    if manifest_mutator:
        manifest_mutator(manifest)
        canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        digest = f"sha256:{hashlib.sha256(canonical).hexdigest()}"
    manifest_bytes = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=canonical_manifest_bytes,
        separators=(",", ":") if canonical_manifest_bytes else None,
    ).encode("utf-8")
    with tarfile.open(bundle, "w:gz") as archive:
        add_bytes(archive, release.MANIFEST_MEMBER, manifest_bytes)
        add_bytes(archive, release.SIGNATURE_MEMBER, signature_bytes)
        for path, (content, mode) in files.items():
            add_bytes(archive, f"payload/{path}", content, mode)
        if unsafe_member is not None:
            archive.addfile(unsafe_member, io.BytesIO(b"x") if unsafe_member.size else None)
    return manifest, digest


def task_envelope(release_id: str, artifact_uri: str, manifest_digest: str, *, kind="release_bundle_apply"):
    value = {
        "kind": kind,
        "manifest_digest": manifest_digest,
        "artifact_uri": artifact_uri,
        "source_commit": "0123456789abcdef",
        "approval_id": "approval-release-1",
        "required_capability": "release_apply_v1",
        "target_node": "worker-1",
        "rollout_wave": "canary",
        "signature": {
            "format": "sshsig",
            "namespace": "kolibri-release",
            "signer_identity": "owner",
        },
    }
    if kind == "release_bundle_apply":
        value["release_id"] = release_id
    else:
        value["failed_release_id"] = "failed-release"
        value["rollback_to_release_id"] = release_id
    approval_payload = {
        "approval_id": "approval-release-1",
        "release_id": release_id if kind == "release_bundle_apply" else "failed-release",
        "manifest_digest": manifest_digest if kind == "release_bundle_apply" else "sha256:" + "b" * 64,
        "release_signature_namespace": "kolibri-release",
        "release_signer_identity": "owner",
        "decision": "approved",
        "allow_rollback": True,
        "rollback": {
            "release_id": release_id if kind == "release_bundle_rollback" else "approved-rollback",
            "manifest_digest": manifest_digest if kind == "release_bundle_rollback" else "sha256:" + "c" * 64,
            "signature_namespace": "kolibri-release",
            "signer_identity": "owner",
        },
        "rollout_plan": [{"name": "canary", "nodes": ["worker-1"]}],
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        "nonce": "approval-nonce-1",
        "signer_identity": "owner",
    }
    approval_payload = release_authority_payload(approval_payload)
    attestation = {
        "schema_version": "kolibri.owner-approval-attestation.v1",
        "payload": approval_payload,
        "signature": "-----BEGIN SSH SIGNATURE-----\nowner-approval-test\n-----END SSH SIGNATURE-----\n",
    }
    value["approval_attestation"] = attestation
    value["approval_attestation_digest"] = approval_attestation_hash(attestation)
    return value


def release_authority_payload(value):
    from ops.release_authority import canonical_owner_approval_payload

    return canonical_owner_approval_payload(value)


def approval_attestation_hash(value):
    from ops.release_authority import approval_attestation_digest

    return approval_attestation_digest(value)


def patch_signature_verifier(monkeypatch, release, *, returncode=0):
    real_run = release.subprocess.run
    calls = []

    def run(command, *args, **kwargs):
        if Path(command[0]).name == "ssh-keygen":
            calls.append((command, kwargs))
            namespace = command[command.index("-n") + 1]
            effective = 0 if namespace == "kolibri-owner-approval" else returncode
            return SimpleNamespace(returncode=effective, stdout=b"", stderr=b"")
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(release.subprocess, "run", run)
    return calls


def prepare_release_case(release, tmp_path, release_id="release-1", *, fail_on_release=""):
    installer, _ = make_installer(release, tmp_path, fail_on_release=fail_on_release)
    bundle = installer.config.artifact_root / "bundles" / f"{release_id}.tar.gz"
    bundle.parent.mkdir()
    artifact_uri = f"artifact://bundles/{release_id}.tar.gz"
    _, digest = build_bundle(release, bundle, release_id, artifact_uri)
    evidence = installer.config.artifact_root / "tasks" / release_id
    evidence.mkdir(parents=True)
    return installer, artifact_uri, digest, evidence


def test_apply_verifies_worker_signature_switches_atomically_and_is_idempotent(
    release_module,
    tmp_path,
    monkeypatch,
):
    release = release_module
    installer, artifact_uri, digest, evidence = prepare_release_case(release, tmp_path)
    signature_calls = patch_signature_verifier(monkeypatch, release)
    envelope = task_envelope("release-1", artifact_uri, digest)
    progress_pulses = []

    first = installer.execute(
        "release_bundle_apply",
        envelope,
        evidence,
        progress_callback=lambda: progress_pulses.append("pulse"),
    )
    second = installer.execute("release_bundle_apply", envelope, evidence)

    assert first["status"] == "completed"
    assert first["manifest_digest"] == digest
    assert first["release_health"]["status"] == "healthy"
    assert first["release_health"]["manifest_digest"] == digest
    assert first["agent_host_runtime"]["included"] is False
    assert installer.config.current_link.resolve().name == "release-1"
    assert second["status"] == "completed"
    assert second["idempotent_reapply"] is True
    assert second["atomic_switch_performed"] is False
    assert len(signature_calls) == 5
    command, kwargs = next(
        call for call in signature_calls if call[0][call[0].index("-n") + 1] == "kolibri-release"
    )
    assert command[command.index("-n") + 1] == "kolibri-release"
    assert command[command.index("-I") + 1] == "owner"
    assert kwargs["input"]
    signer_snapshot = Path(command[command.index("-f") + 1])
    assert signer_snapshot != installer.config.allowed_signers
    assert not signer_snapshot.exists()
    assert "verified_by_controller" not in str(envelope)
    assert len(progress_pulses) >= 5
    log_text = (evidence / "release-installer.jsonl").read_text(encoding="utf-8")
    assert artifact_uri not in log_text
    assert "detached-sshsig" not in log_text


def test_signed_agent_host_payload_emits_activation_handoff_evidence(
    release_module, tmp_path, monkeypatch
):
    release = release_module
    installer, _ = make_installer(release, tmp_path)
    artifact_uri = "artifact://bundles/agent-host-v2.tar.gz"
    bundle = installer.config.artifact_root / "bundles" / "agent-host-v2.tar.gz"
    bundle.parent.mkdir()
    runtime_bytes = b"#!/usr/bin/python3\nprint('agent-host-v2')\n"
    response_profile_bytes = (
        Path(release.__file__).parent / "mimo" / "kolibri-response-only.md"
    ).read_bytes()
    _, digest = build_bundle(
        release,
        bundle,
        "agent-host-v2",
        artifact_uri,
        files={
            "ops/agent_host.py": (runtime_bytes, 0o755),
            "ops/mimo/kolibri-response-only.md": (response_profile_bytes, 0o644),
        },
    )
    evidence = installer.config.artifact_root / "tasks" / "agent-host-v2"
    evidence.mkdir(parents=True)
    patch_signature_verifier(monkeypatch, release)

    result = installer.execute(
        "release_bundle_apply",
        task_envelope("agent-host-v2", artifact_uri, digest),
        evidence,
    )

    assert result["agent_host_runtime"] == {
        "included": True,
        "runtime_path": "ops/agent_host.py",
        "runtime_sha256": hashlib.sha256(runtime_bytes).hexdigest(),
        "response_profile_included": True,
        "response_profile_path": "ops/mimo/kolibri-response-only.md",
        "response_profile_sha256": hashlib.sha256(response_profile_bytes).hexdigest(),
        "release_id": "agent-host-v2",
        "manifest_digest": digest,
    }


def test_signed_agent_host_payload_without_response_profile_is_rejected(
    release_module, tmp_path, monkeypatch
):
    release = release_module
    installer, _ = make_installer(release, tmp_path)
    artifact_uri = "artifact://bundles/agent-host-missing-profile.tar.gz"
    bundle = installer.config.artifact_root / "bundles" / "agent-host-missing-profile.tar.gz"
    bundle.parent.mkdir()
    _, digest = build_bundle(
        release,
        bundle,
        "agent-host-missing-profile",
        artifact_uri,
        files={"ops/agent_host.py": (b"#!/usr/bin/python3\n", 0o755)},
    )
    evidence = installer.config.artifact_root / "tasks" / "agent-host-missing-profile"
    evidence.mkdir(parents=True)
    patch_signature_verifier(monkeypatch, release)

    with pytest.raises(release.ReleaseInstallError) as failure:
        installer.execute(
            "release_bundle_apply",
            task_envelope("agent-host-missing-profile", artifact_uri, digest),
            evidence,
        )

    assert failure.value.code == "release_agent_host_profile_missing"


def test_real_openssh_signature_is_verified_end_to_end(release_module, tmp_path):
    release = release_module
    ssh_keygen = shutil.which("ssh-keygen")
    if not ssh_keygen:
        pytest.skip("ssh-keygen is unavailable")
    installer, _ = make_installer(release, tmp_path)
    key_path = tmp_path / "release-signing-key"
    generated = subprocess.run(
        [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(key_path)],
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert generated.returncode == 0, generated.stderr.decode("utf-8", errors="replace")
    public_key = (tmp_path / "release-signing-key.pub").read_text(encoding="utf-8").strip()
    installer.config.allowed_signers.write_text(f"owner {public_key}\n", encoding="utf-8")
    installer.config.owner_allowed_signers.write_text(f"owner {public_key}\n", encoding="utf-8")

    artifact_uri = "artifact://real-signed.tar.gz"
    files = {"bin/kolibri-app": (b"real-signed-release", 0o755)}
    manifest, digest = canonical_manifest(release, "real-signed", artifact_uri, files)
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    message_path = tmp_path / "manifest.canonical.json"
    message_path.write_bytes(canonical)
    signed = subprocess.run(
        [
            ssh_keygen,
            "-Y",
            "sign",
            "-f",
            str(key_path),
            "-n",
            release.RELEASE_SIGNATURE_NAMESPACE,
            str(message_path),
        ],
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert signed.returncode == 0, signed.stderr.decode("utf-8", errors="replace")
    signature = Path(f"{message_path}.sig").read_bytes()
    bundle = installer.config.artifact_root / "real-signed.tar.gz"
    build_bundle(
        release,
        bundle,
        "real-signed",
        artifact_uri,
        files=files,
        signature_bytes=signature,
    )
    evidence = installer.config.artifact_root / "task-real-signed"
    evidence.mkdir()
    envelope = task_envelope("real-signed", artifact_uri, digest)
    from ops.release_authority import canonical_owner_approval_bytes

    approval_message = tmp_path / "approval.canonical.json"
    approval_message.write_bytes(
        canonical_owner_approval_bytes(envelope["approval_attestation"]["payload"])
    )
    approval_signed = subprocess.run(
        [
            ssh_keygen,
            "-Y",
            "sign",
            "-f",
            str(key_path),
            "-n",
            "kolibri-owner-approval",
            str(approval_message),
        ],
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert approval_signed.returncode == 0, approval_signed.stderr.decode("utf-8", errors="replace")
    envelope["approval_attestation"]["signature"] = Path(f"{approval_message}.sig").read_text(
        encoding="utf-8"
    )
    envelope["approval_attestation_digest"] = approval_attestation_hash(
        envelope["approval_attestation"]
    )

    result = installer.execute(
        "release_bundle_apply",
        envelope,
        evidence,
    )

    assert result["status"] == "completed"
    assert result["release_health"]["status"] == "healthy"
    assert installer.config.current_link.resolve().name == "real-signed"


@pytest.mark.parametrize("unsafe_name", ["../escape", "payload/../../escape"])
def test_bundle_path_traversal_is_rejected_before_switch(
    release_module,
    tmp_path,
    monkeypatch,
    unsafe_name,
):
    release = release_module
    installer, _ = make_installer(release, tmp_path)
    bundle = installer.config.artifact_root / "unsafe.tar.gz"
    artifact_uri = "artifact://unsafe.tar.gz"
    info = tarfile.TarInfo(unsafe_name)
    info.size = 1
    build_bundle(release, bundle, "unsafe-release", artifact_uri, unsafe_member=info)
    patch_signature_verifier(monkeypatch, release)
    evidence = installer.config.artifact_root / "task"
    evidence.mkdir()

    with pytest.raises(release.ReleaseInstallError, match="release_bundle_path_traversal"):
        installer.execute(
            "release_bundle_apply",
            task_envelope("unsafe-release", artifact_uri, "sha256:" + "0" * 64),
            evidence,
        )
    assert not os.path.lexists(installer.config.current_link)


def test_symlink_member_is_rejected(release_module, tmp_path, monkeypatch):
    release = release_module
    installer, _ = make_installer(release, tmp_path)
    bundle = installer.config.artifact_root / "symlink.tar.gz"
    artifact_uri = "artifact://symlink.tar.gz"
    info = tarfile.TarInfo("payload/link")
    info.type = tarfile.SYMTYPE
    info.linkname = "../../outside"
    build_bundle(release, bundle, "symlink-release", artifact_uri, unsafe_member=info)
    patch_signature_verifier(monkeypatch, release)
    evidence = installer.config.artifact_root / "task"
    evidence.mkdir()

    with pytest.raises(release.ReleaseInstallError, match="release_bundle_unsafe_member_type"):
        installer.execute(
            "release_bundle_apply",
            task_envelope("symlink-release", artifact_uri, "sha256:" + "0" * 64),
            evidence,
        )


def test_artifact_symlink_escape_is_rejected(release_module, tmp_path, monkeypatch):
    release = release_module
    installer, _ = make_installer(release, tmp_path)
    outside = tmp_path / "outside.tar.gz"
    artifact_uri = "artifact://escape.tar.gz"
    _, digest = build_bundle(release, outside, "escape-release", artifact_uri)
    (installer.config.artifact_root / "escape.tar.gz").symlink_to(outside)
    evidence = installer.config.artifact_root / "task"
    evidence.mkdir()
    patch_signature_verifier(monkeypatch, release)

    with pytest.raises(release.ReleaseInstallError, match="release_artifact_boundary_violation"):
        installer.execute(
            "release_bundle_apply",
            task_envelope("escape-release", artifact_uri, digest),
            evidence,
        )


@pytest.mark.parametrize(
    "uri",
    [
        "https://user@example.com/release.tar.gz",
        "https://example.com/release.tar.gz?token=secret",
        "https://example.com/release.tar.gz#fragment",
        "http://example.com/release.tar.gz",
    ],
)
def test_remote_artifact_uri_is_credential_free_https_only(release_module, uri):
    with pytest.raises(release_module.ReleaseInstallError, match="release_artifact_uri_invalid"):
        release_module._validate_artifact_uri(uri)


def test_worker_rejects_bad_signature_even_when_controller_claims_verified(
    release_module,
    tmp_path,
    monkeypatch,
):
    release = release_module
    installer, artifact_uri, digest, evidence = prepare_release_case(release, tmp_path)
    calls = patch_signature_verifier(monkeypatch, release, returncode=1)
    envelope = task_envelope("release-1", artifact_uri, digest)
    envelope["signature"]["verified_by_controller"] = True

    with pytest.raises(release.ReleaseInstallError, match="release_signature_invalid"):
        installer.execute("release_bundle_apply", envelope, evidence)
    assert len(calls) == 2
    assert not os.path.lexists(installer.config.current_link)


def test_manifest_bytes_must_be_canonical(release_module, tmp_path, monkeypatch):
    release = release_module
    installer, _ = make_installer(release, tmp_path)
    artifact_uri = "artifact://noncanonical.tar.gz"
    bundle = installer.config.artifact_root / "noncanonical.tar.gz"
    _, digest = build_bundle(
        release,
        bundle,
        "noncanonical-release",
        artifact_uri,
        canonical_manifest_bytes=False,
    )
    evidence = installer.config.artifact_root / "task"
    evidence.mkdir()
    patch_signature_verifier(monkeypatch, release)

    with pytest.raises(release.ReleaseInstallError, match="release_manifest_not_canonical"):
        installer.execute(
            "release_bundle_apply",
            task_envelope("noncanonical-release", artifact_uri, digest),
            evidence,
        )


def test_manifest_and_payload_digest_mismatches_fail_closed(release_module, tmp_path, monkeypatch):
    release = release_module
    installer, artifact_uri, _, evidence = prepare_release_case(release, tmp_path)
    patch_signature_verifier(monkeypatch, release)

    with pytest.raises(release.ReleaseInstallError, match="release_manifest_digest_mismatch"):
        installer.execute(
            "release_bundle_apply",
            task_envelope("release-1", artifact_uri, "sha256:" + "f" * 64),
            evidence,
        )

    bad_bundle = installer.config.artifact_root / "bundles" / "bad-payload.tar.gz"
    bad_uri = "artifact://bundles/bad-payload.tar.gz"

    def corrupt_digest(manifest):
        manifest["files"][0]["sha256"] = "0" * 64

    _, bad_digest = build_bundle(
        release,
        bad_bundle,
        "bad-payload",
        bad_uri,
        manifest_mutator=corrupt_digest,
    )
    bad_evidence = installer.config.artifact_root / "tasks" / "bad-payload"
    bad_evidence.mkdir()
    with pytest.raises(release.ReleaseInstallError, match="release_payload_digest_mismatch"):
        installer.execute(
            "release_bundle_apply",
            task_envelope("bad-payload", bad_uri, bad_digest),
            bad_evidence,
        )


@pytest.mark.parametrize(
    ("field", "expected_error"),
    [
        ("size_bytes", "release_payload_size_mismatch"),
        ("mode", "release_payload_mode_mismatch"),
    ],
)
def test_payload_size_and_mode_must_match_signed_manifest(
    release_module,
    tmp_path,
    monkeypatch,
    field,
    expected_error,
):
    release = release_module
    installer, _ = make_installer(release, tmp_path)
    bundle = installer.config.artifact_root / "mismatch.tar.gz"
    artifact_uri = "artifact://mismatch.tar.gz"

    def mutate(manifest):
        if field == "size_bytes":
            manifest["files"][0]["size_bytes"] += 1
        else:
            manifest["files"][0]["mode"] = "0644"

    _, digest = build_bundle(
        release,
        bundle,
        "mismatch-release",
        artifact_uri,
        manifest_mutator=mutate,
    )
    evidence = installer.config.artifact_root / "task"
    evidence.mkdir()
    patch_signature_verifier(monkeypatch, release)

    with pytest.raises(release.ReleaseInstallError, match=expected_error):
        installer.execute(
            "release_bundle_apply",
            task_envelope("mismatch-release", artifact_uri, digest),
            evidence,
        )


def test_failed_post_health_rolls_current_symlink_back_atomically(release_module, tmp_path, monkeypatch):
    release = release_module
    installer, artifact_uri, digest, evidence = prepare_release_case(
        release,
        tmp_path,
        release_id="bad-release",
        fail_on_release="bad-release",
    )
    old_release = installer.config.release_root / "old-release"
    old_release.mkdir()
    installer.config.current_link.symlink_to(old_release)
    patch_signature_verifier(monkeypatch, release)

    with pytest.raises(release.ReleaseInstallError, match="release_post_health_failed") as captured:
        installer.execute(
            "release_bundle_apply",
            task_envelope("bad-release", artifact_uri, digest),
            evidence,
        )

    assert installer.config.current_link.resolve() == old_release.resolve()
    assert captured.value.evidence["rollback"]["status"] == "completed"
    assert captured.value.evidence["release_health"]["status"] == "failed"
    assert (installer.config.release_root / "bad-release").is_dir()


def test_failed_candidate_health_never_switches_current_or_restarts_services(
    release_module,
    tmp_path,
    monkeypatch,
):
    release = release_module
    installer, artifact_uri, digest, evidence = prepare_release_case(
        release,
        tmp_path,
        release_id="candidate-release",
    )
    old_release = installer.config.release_root / "old-release"
    old_release.mkdir()
    installer.config.current_link.symlink_to(old_release)
    candidate_check = write_executable(
        tmp_path / "candidate-check",
        "raise SystemExit(1)",
    )
    policy = json.loads(installer.config.policy_path.read_text(encoding="utf-8"))
    policy["pre_activate"] = [{
        "name": "candidate",
        "argv": [str(candidate_check), "{release_dir}"],
        "timeout_seconds": 1,
    }]
    installer.config.policy_path.write_text(json.dumps(policy), encoding="utf-8")
    patch_signature_verifier(monkeypatch, release)
    monkeypatch.setattr(
        installer,
        "_restart_services",
        lambda *args, **kwargs: pytest.fail("candidate failure must precede service restart"),
    )

    with pytest.raises(release.ReleaseInstallError, match="release_candidate_health_failed") as captured:
        installer.execute(
            "release_bundle_apply",
            task_envelope("candidate-release", artifact_uri, digest),
            evidence,
        )

    assert installer.config.current_link.resolve() == old_release.resolve()
    assert (installer.config.release_root / "candidate-release").is_dir()
    assert captured.value.evidence["rollback"] == {
        "status": "not_required",
        "reason": "activation_not_started",
    }
    assert captured.value.evidence["health_checks"]["candidate"][0]["status"] == "failed"


def test_candidate_policy_requires_complete_fixed_service_profile(release_module, tmp_path):
    release = release_module
    installer, health = make_installer(release, tmp_path)
    policy = json.loads(installer.config.policy_path.read_text(encoding="utf-8"))
    policy.update({
        "services": ["one.service", "two.service"],
        "default_services": ["one.service", "two.service"],
        "pre_activate": [{
            "name": "candidate",
            "argv": [str(health), "{release_dir}"],
            "timeout_seconds": 5,
        }],
    })
    installer.config.policy_path.write_text(json.dumps(policy), encoding="utf-8")
    loaded = release.load_release_policy(installer.config.policy_path)

    with pytest.raises(release.ReleaseInstallError, match="release_service_profile_mismatch"):
        installer._selected_services(("one.service",), loaded)
    assert installer._selected_services(None, loaded) == ("one.service", "two.service")


def test_worker_rejects_signed_bundle_missing_local_required_payload(
    release_module,
    tmp_path,
    monkeypatch,
):
    release = release_module
    installer, artifact_uri, digest, evidence = prepare_release_case(
        release,
        tmp_path,
        release_id="incomplete-profile",
    )
    policy = json.loads(installer.config.policy_path.read_text(encoding="utf-8"))
    policy["required_payload_paths"] = ["ops/factory_control.py"]
    installer.config.policy_path.write_text(json.dumps(policy), encoding="utf-8")
    patch_signature_verifier(monkeypatch, release)

    with pytest.raises(release.ReleaseInstallError, match="release_required_payload_missing"):
        installer.execute(
            "release_bundle_apply",
            task_envelope("incomplete-profile", artifact_uri, digest),
            evidence,
        )

    assert not os.path.lexists(installer.config.current_link)
    assert not (installer.config.release_root / "incomplete-profile").exists()


def test_worker_binds_required_release_marker_to_signed_release_id(
    release_module,
    tmp_path,
    monkeypatch,
):
    release = release_module
    installer, _ = make_installer(release, tmp_path)
    policy = json.loads(installer.config.policy_path.read_text(encoding="utf-8"))
    policy["required_payload_paths"] = ["RELEASE_ID"]
    installer.config.policy_path.write_text(json.dumps(policy), encoding="utf-8")
    artifact_uri = "artifact://marker-mismatch.tar.gz"
    bundle = installer.config.artifact_root / "marker-mismatch.tar.gz"
    _, digest = build_bundle(
        release,
        bundle,
        "marker-release",
        artifact_uri,
        files={"RELEASE_ID": (b"different-release\n", 0o644)},
    )
    evidence = installer.config.artifact_root / "marker-task"
    evidence.mkdir()
    patch_signature_verifier(monkeypatch, release)

    with pytest.raises(release.ReleaseInstallError, match="release_id_marker_invalid"):
        installer.execute(
            "release_bundle_apply",
            task_envelope("marker-release", artifact_uri, digest),
            evidence,
        )

    assert not os.path.lexists(installer.config.current_link)


def test_health_check_retries_same_fixed_argv_until_it_passes(
    release_module,
    tmp_path,
    monkeypatch,
):
    release = release_module
    health_script = write_executable(tmp_path / "eventually-healthy", "raise SystemExit(0)")
    clock = {"now": 0.0}
    calls: list[tuple[tuple[str, ...], float]] = []
    pulses: list[float] = []

    monkeypatch.setattr(release.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        release.time,
        "sleep",
        lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )

    def fake_bounded_process(cls, argv, timeout_seconds, progress):
        calls.append((tuple(argv), timeout_seconds))
        return 1 if len(calls) == 1 else 0

    monkeypatch.setattr(
        release.ReleaseInstaller,
        "_run_bounded_process",
        classmethod(fake_bounded_process),
    )
    progress = release.ProgressReporter(
        lambda: pulses.append(clock["now"]),
        interval_seconds=0,
    )
    check = release.HealthCheck(
        name="post:backend",
        argv=(str(health_script), "--fixed-health-contract"),
        timeout_seconds=2,
    )

    result = release.ReleaseInstaller._run_health_checks((check,), progress)

    assert result == [
        {
            "name": "post:backend",
            "status": "passed",
            "attempts": 2,
            "duration_ms": 250,
        }
    ]
    assert [item[0] for item in calls] == [check.argv, check.argv]
    assert calls[0][1] == pytest.approx(2.0)
    assert calls[1][1] == pytest.approx(1.75)
    assert pulses


def test_health_check_exhausts_single_total_timeout_and_fails_closed(
    release_module,
    tmp_path,
    monkeypatch,
):
    release = release_module
    health_script = write_executable(tmp_path / "always-unhealthy", "raise SystemExit(1)")
    clock = {"now": 0.0}
    calls: list[tuple[tuple[str, ...], float]] = []
    pulses: list[float] = []

    monkeypatch.setattr(release.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        release.time,
        "sleep",
        lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )

    def fake_bounded_process(cls, argv, timeout_seconds, progress):
        calls.append((tuple(argv), timeout_seconds))
        return 22

    monkeypatch.setattr(
        release.ReleaseInstaller,
        "_run_bounded_process",
        classmethod(fake_bounded_process),
    )
    progress = release.ProgressReporter(
        lambda: pulses.append(clock["now"]),
        interval_seconds=0,
    )
    check = release.HealthCheck(
        name="post:backend",
        argv=(str(health_script), "--fixed-health-contract"),
        timeout_seconds=1,
    )

    result = release.ReleaseInstaller._run_health_checks((check,), progress)

    assert result == [
        {
            "name": "post:backend",
            "status": "failed",
            "attempts": 4,
            "duration_ms": 1000,
        }
    ]
    assert [item[0] for item in calls] == [check.argv] * 4
    assert [item[1] for item in calls] == pytest.approx([1.0, 0.75, 0.5, 0.25])
    assert len(pulses) == 4
    assert release.HEALTH_RETRY_DELAY_SECONDS <= 0.5
    assert "argv" not in result[0]
    assert str(health_script) not in json.dumps(result)


def test_legacy_compatibility_exit_is_success_only_for_explicit_rollback(
    release_module,
    tmp_path,
    monkeypatch,
):
    release = release_module
    health_script = write_executable(tmp_path / "rollback-compat", "raise SystemExit(10)")
    check = release.HealthCheck(
        name="post:control-plane",
        argv=(str(health_script), "{release_kind}"),
        timeout_seconds=1,
    )
    monkeypatch.setattr(
        release.ReleaseInstaller,
        "_run_bounded_process",
        classmethod(lambda cls, argv, timeout, progress: 10),
    )

    rollback = release.ReleaseInstaller._run_health_checks(
        (check,),
        release.ProgressReporter(None),
        replacements={"{release_kind}": "rollback"},
    )

    assert rollback[0]["name"] == "post:control-plane"
    assert rollback[0]["status"] == "passed"
    assert rollback[0]["attempts"] == 1
    assert rollback[0]["compatibility_mode"] == "legacy-rollback-contract"


def test_legacy_baseline_exit_is_success_only_for_explicit_local_policy_flag(
    release_module,
    tmp_path,
    monkeypatch,
):
    release = release_module
    health_script = write_executable(tmp_path / "baseline-compat", "raise SystemExit(11)")
    allowed = release.HealthCheck(
        name="pre:control-plane",
        argv=(str(health_script), "--allow-legacy-baseline"),
        timeout_seconds=1,
    )
    denied = release.HealthCheck(
        name="pre:control-plane-without-contract",
        argv=(str(health_script),),
        timeout_seconds=1,
    )
    monkeypatch.setattr(
        release.ReleaseInstaller,
        "_run_bounded_process",
        classmethod(lambda cls, argv, timeout, progress: 11),
    )

    accepted = release.ReleaseInstaller._run_health_checks(
        (allowed,),
        release.ProgressReporter(None),
    )
    rejected = release.ReleaseInstaller._run_health_checks(
        (denied,),
        release.ProgressReporter(None),
    )

    assert accepted[0]["status"] == "passed"
    assert accepted[0]["compatibility_mode"] == "legacy-baseline-contract"
    assert rejected[0]["status"] == "failed"
    assert "compatibility_mode" not in rejected[0]


def test_explicit_rollback_kind_switches_to_signed_target(release_module, tmp_path, monkeypatch):
    release = release_module
    installer, artifact_uri, digest, evidence = prepare_release_case(
        release,
        tmp_path,
        release_id="known-good",
    )
    failed = installer.config.release_root / "failed-release"
    failed.mkdir()
    installer.config.current_link.symlink_to(failed)
    patch_signature_verifier(monkeypatch, release)

    result = installer.execute(
        "release_bundle_rollback",
        task_envelope("known-good", artifact_uri, digest, kind="release_bundle_rollback"),
        evidence,
    )

    assert result["status"] == "completed"
    assert result["rollback"]["status"] == "completed"
    assert result["rollback"]["from_release_id"] == "failed-release"
    assert installer.config.current_link.resolve().name == "known-good"


def test_task_commands_and_non_allowlisted_services_are_never_executed(
    release_module, tmp_path, monkeypatch
):
    release = release_module
    installer, artifact_uri, digest, evidence = prepare_release_case(release, tmp_path)
    envelope = task_envelope("release-1", artifact_uri, digest)
    envelope["commands"] = [["/bin/sh", "-c", "touch /tmp/forbidden"]]
    with pytest.raises(release.ReleaseInstallError, match="release_task_command_forbidden"):
        installer.execute("release_bundle_apply", envelope, evidence)

    envelope = task_envelope("release-1", artifact_uri, digest)
    envelope["services"] = ["not-allowed.service"]
    patch_signature_verifier(monkeypatch, release)
    with pytest.raises(release.ReleaseInstallError, match="release_service_not_allowed"):
        installer.execute("release_bundle_apply", envelope, evidence)


def test_local_policy_cannot_restart_agent_host(release_module, tmp_path):
    release = release_module
    installer, health_script = make_installer(release, tmp_path)
    write_policy(
        release,
        installer.config.policy_path,
        health_script,
        services=["kolibri-agent-host.service"],
        defaults=["kolibri-agent-host.service"],
    )

    with pytest.raises(release.ReleaseInstallError, match="release_policy_services_invalid"):
        release.load_release_policy(installer.config.policy_path)
    assert installer.prerequisite_status()["status"] == "unavailable"


def test_release_policy_accepts_trusted_versioned_executable_symlink(
    release_module,
    tmp_path,
):
    release = release_module
    trusted = tmp_path / "trusted-bin"
    trusted.mkdir(mode=0o700)
    target = write_executable(trusted / "python3.12", "raise SystemExit(0)")
    link = trusted / "python3"
    link.symlink_to(target.name)
    policy = tmp_path / "release-policy.json"
    write_policy(
        release,
        policy,
        link,
        services=["kolibri-backend.service"],
        defaults=["kolibri-backend.service"],
    )

    loaded = release.load_release_policy(policy)

    assert loaded.pre_health[0].argv[0] == str(link)


def test_release_policy_rejects_executable_symlink_in_untrusted_directory(
    release_module,
    tmp_path,
):
    release = release_module
    untrusted = tmp_path / "untrusted-bin"
    untrusted.mkdir(mode=0o777)
    untrusted.chmod(0o777)
    target = write_executable(tmp_path / "python3.12", "raise SystemExit(0)")
    link = untrusted / "python3"
    link.symlink_to(target)
    policy = tmp_path / "release-policy.json"
    write_policy(
        release,
        policy,
        link,
        services=["kolibri-backend.service"],
        defaults=["kolibri-backend.service"],
    )

    with pytest.raises(
        release.ReleaseInstallError,
        match="release_policy_health_executable_unavailable",
    ):
        release.load_release_policy(policy)


def test_health_runner_executes_trusted_versioned_executable_symlink(
    release_module, tmp_path
):
    release = release_module
    trusted = tmp_path / "trusted-bin"
    trusted.mkdir(mode=0o755)
    target = write_executable(trusted / "python3.12", "raise SystemExit(0)")
    link = trusted / "python3"
    link.symlink_to(target.name)
    check = release.HealthCheck(
        name="portable-python",
        argv=(str(link),),
        timeout_seconds=2,
    )

    results = release.ReleaseInstaller._run_health_checks(
        (check,), release.ProgressReporter(None)
    )

    assert results == [
        {
            "name": "portable-python",
            "status": "passed",
            "attempts": 1,
            "duration_ms": results[0]["duration_ms"],
        }
    ]


def test_capability_requires_real_local_prerequisites(
    release_module, tmp_path, monkeypatch, canonical_home_control_plane
):
    release = release_module
    installer, health_script = make_installer(release, tmp_path)
    monkeypatch.setenv("KOLIBRI_ARTIFACT_ROOT", str(installer.config.artifact_root))
    monkeypatch.setenv("KOLIBRI_RELEASE_ROOT", str(installer.config.release_root))
    monkeypatch.setenv("KOLIBRI_RELEASE_CURRENT_LINK", str(installer.config.current_link))
    monkeypatch.setenv("KOLIBRI_RELEASE_ALLOWED_SIGNERS", str(installer.config.allowed_signers))
    monkeypatch.setenv(
        "KOLIBRI_OWNER_APPROVAL_ALLOWED_SIGNERS",
        str(installer.config.owner_allowed_signers),
    )
    monkeypatch.setenv("KOLIBRI_RELEASE_POLICY", str(installer.config.policy_path))
    monkeypatch.setenv("KOLIBRI_RELEASE_SSH_KEYGEN", str(installer.config.ssh_keygen))
    agent = load_module("agent_host_release_capability", ROOT / "ops" / "agent_host.py")

    class FakeHelper:
        @classmethod
        def from_environment(cls):
            return cls()

        def prerequisite_status(self):
            return installer.prerequisite_status()

    monkeypatch.setattr(agent, "ReleaseHelperClient", FakeHelper)
    args = argparse.Namespace(
        control_url=canonical_home_control_plane,
        node_id="worker-1",
        agent_id="worker-1-agent",
        capabilities="read_only_probe,release_apply_v1",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(installer.config.artifact_root),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )

    host = agent.AgentHost(args)
    assert "release_apply_v1" in host.capabilities
    installer.config.allowed_signers.unlink()
    host.refresh_release_installer_capability()
    assert "release_apply_v1" not in host.capabilities
    assert host.release_installer_status["status"] == "unavailable"
    assert health_script.is_file()


def test_agent_host_dispatches_release_kind_and_completes_only_with_healthy_result(
    tmp_path, canonical_home_control_plane
):
    agent = load_module("agent_host_release_dispatch", ROOT / "ops" / "agent_host.py")
    args = argparse.Namespace(
        control_url=canonical_home_control_plane,
        node_id="worker-1",
        agent_id="worker-1-agent",
        capabilities="read_only_probe",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )

    class FakeInstaller:
        health_status = "healthy"

        def execute(self, kind, envelope, evidence_dir, *, progress_callback=None):
            assert kind == "release_bundle_apply"
            assert envelope["release_id"] == "release-1"
            assert envelope["task_id"] in {
                "release-task-1",
                "release-task-unhealthy",
            }
            assert envelope["attempt_id"] == f'{envelope["task_id"]}-attempt-1'
            assert evidence_dir.is_relative_to(tmp_path / "artifacts")
            assert progress_callback is not None
            progress_callback()
            return {
                "status": "completed",
                "kind": kind,
                "release_id": "release-1",
                "manifest_digest": "sha256:" + "a" * 64,
                "release_health": {
                    "status": self.health_status,
                    "release_id": "release-1",
                    "manifest_digest": "sha256:" + "a" * 64,
                },
                "release_evidence": {
                    "schema_version": "kolibri.release-evidence-ref.v1",
                    "scope": "privileged_helper",
                    "retention": "root_only",
                    "ref": "sha256:" + "b" * 64,
                },
                "changed_files": [],
            }

    class Host(agent.AgentHost):
        def __init__(self):
            super().__init__(args)
            self.posts = []
            self.release_helper = FakeInstaller()
            self.release_installer_status = {"status": "available", "capability": "release_apply_v1", "reasons": []}
            self.capabilities.append("release_apply_v1")
            self._last_node_heartbeat = agent.time.time()

        def post(self, path, body):
            self.posts.append((path, body))
            return body

    envelope = task_envelope("release-1", "artifact://bundles/release-1.tar.gz", "sha256:" + "a" * 64)
    task = {
        "task_id": "release-task-1",
        "kind": "release_bundle_apply",
        "attempt": 1,
        "attempt_id": "release-task-1-attempt-1",
        "max_retries": 1,
        "envelope": envelope,
    }
    host = Host()

    host.run_task(task)

    complete = [(path, body) for path, body in host.posts if path.endswith("/complete")]
    failed = [(path, body) for path, body in host.posts if path.endswith("/fail")]
    assert len(complete) == 1
    assert failed == []
    assert complete[0][1]["result"]["release_health"]["status"] == "healthy"
    assert complete[0][1]["result"]["manifest_digest"] == "sha256:" + "a" * 64
    assert complete[0][1]["result"]["release_evidence"]["scope"] == "privileged_helper"
    assert "release_installer" not in complete[0][1]["result"]["log_paths"]

    host.posts.clear()
    host.release_helper.health_status = "failed"
    unhealthy_task = {
        **task,
        "task_id": "release-task-unhealthy",
        "attempt_id": "release-task-unhealthy-attempt-1",
    }
    host.run_task(unhealthy_task)

    complete = [(path, body) for path, body in host.posts if path.endswith("/complete")]
    failed = [(path, body) for path, body in host.posts if path.endswith("/fail")]
    assert complete == []
    assert len(failed) == 1
    assert failed[0][1]["error_type"] == "release_health_evidence_invalid"
    assert failed[0][1]["error"] == "release_health_evidence_invalid"
