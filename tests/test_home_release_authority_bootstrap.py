from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from ops.home_release_authority_bootstrap import (
    BootstrapError,
    HomeReleaseAuthorityBootstrap,
    _required_parent_is_safe,
    normalize_public_signer,
)
from ops.home_release_authority_preflight import PreflightError, preflight


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_KEY_BODY = (
    "ssh-ed25519 "
    "AAAAC3NzaC1lZDI1NTE5AAAAIGFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFh"
)


class FakeRunner:
    def __init__(self, *, fail_helper_probe: bool = False):
        self.fail_helper_probe = fail_helper_probe
        self.socket_enabled = False
        self.socket_active = False
        self.service_active = False
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, *, check=True, timeout=30):
        del timeout
        command = tuple(str(item) for item in argv)
        self.calls.append(command)
        returncode = 0
        stdout = ""
        if "-lf" in command:
            returncode = 0
        elif len(command) >= 2 and command[1] == "is-enabled":
            stdout = "enabled\n" if self.socket_enabled else "disabled\n"
            returncode = 0 if self.socket_enabled else 1
        elif len(command) >= 4 and command[1:3] == ("is-active", "--quiet"):
            unit = command[3]
            active = self.socket_active if unit.endswith(".socket") else self.service_active
            returncode = 0 if active else 3
        elif len(command) >= 3 and command[1] in {"start", "restart", "stop"}:
            action, unit = command[1], command[2]
            active = action != "stop"
            if unit.endswith(".socket"):
                self.socket_active = active
            else:
                self.service_active = active
        elif len(command) >= 3 and command[1] == "enable":
            self.socket_enabled = True
        elif len(command) >= 3 and command[1] in {"disable", "mask"}:
            self.socket_enabled = False
        elif self.fail_helper_probe and "kolibri-agent" in command and "-c" in command:
            returncode = 23
        completed = subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="")
        if check and returncode != 0:
            raise BootstrapError("release_authority_command_failed")
        return completed


class ActivationRunner:
    def __init__(self, *, fail_step: str | None = None, probe_returncode: int = 0):
        self.fail_step = fail_step
        self.probe_returncode = probe_returncode
        self.calls: list[tuple[tuple[str, ...], bool]] = []

    @staticmethod
    def step(command: tuple[str, ...]) -> str:
        if len(command) >= 2 and command[1] == "daemon-reload":
            return "daemon_reload"
        if len(command) >= 2 and command[1] == "enable":
            return "enable"
        if len(command) >= 3 and command[1:3] == ("restart", "kolibri-release-helper.socket"):
            return "socket_restart"
        if len(command) >= 3 and command[1:3] == ("restart", "kolibri-release-helper.service"):
            return "service_restart"
        if len(command) >= 4 and command[1:3] == ("is-active", "--quiet"):
            return "socket_active" if command[3].endswith(".socket") else "service_active"
        if "kolibri-agent" in command and "-c" in command:
            return "socket_probe"
        return "unknown"

    def run(self, argv, *, check=True, timeout=30):
        del timeout
        command = tuple(str(item) for item in argv)
        self.calls.append((command, check))
        step = self.step(command)
        if step == "socket_probe":
            returncode = self.probe_returncode
        else:
            returncode = 1 if step == self.fail_step else 0
        return subprocess.CompletedProcess(
            command,
            returncode,
            stdout="output-must-not-be-emitted",
            stderr="error-output-must-not-be-emitted",
        )


def prepare_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    for relative in (
        "usr/local/lib",
        "etc/systemd/system",
        "var/lib",
        "opt",
        "var/backups",
        "run/lock",
    ):
        (root / relative).mkdir(parents=True, mode=0o755)
    return root


def parent_stat(mode: int, *, uid: int = 0, gid: int = 0):
    class ParentStat:
        st_mode = stat.S_IFDIR | mode
        st_uid = uid
        st_gid = gid

    return ParentStat()


def test_canonical_sticky_run_lock_is_the_only_writable_parent_exception():
    assert _required_parent_is_safe(
        "/run/lock", parent_stat(0o1777), production_root=True
    )
    assert not _required_parent_is_safe(
        "/run/lock", parent_stat(0o0777), production_root=True
    )
    assert not _required_parent_is_safe(
        "/run/lock", parent_stat(0o1770), production_root=True
    )
    assert not _required_parent_is_safe(
        "/var/lib", parent_stat(0o1777), production_root=True
    )
    assert _required_parent_is_safe(
        "/var/lib", parent_stat(0o0755), production_root=True
    )


def test_release_helper_socket_parent_allows_allowed_user_traversal():
    socket_unit = (ROOT / "ops/systemd/kolibri-release-helper.socket").read_text(
        encoding="utf-8"
    )

    assert "SocketGroup=kolibri-agent" in socket_unit
    assert "SocketMode=0660" in socket_unit
    assert "DirectoryMode=0755" in socket_unit
    assert "DirectoryMode=0750" not in socket_unit


def write_inputs(tmp_path: Path, *, home_ip: str = "10.77.0.9") -> tuple[Path, Path]:
    manifest = tmp_path / "peers.json"
    manifest.write_text(
        json.dumps(
            {
                "peers": {
                    "dynamic-record": {"node_id": "home", "mesh_ip": home_ip},
                    "worker-record": {"node_id": "worker-a", "mesh_ip": "10.77.0.10"},
                }
            }
        ),
        encoding="utf-8",
    )
    public_key = tmp_path / "signer.pub"
    public_key.write_text(f"{PUBLIC_KEY_BODY} ignored-comment\n", encoding="ascii")
    return manifest, public_key


def bootstrap_for(
    tmp_path: Path,
    *,
    runner: FakeRunner | None = None,
    home_ip: str = "10.77.0.9",
) -> tuple[HomeReleaseAuthorityBootstrap, Path, FakeRunner]:
    root = prepare_root(tmp_path)
    manifest, public_key = write_inputs(tmp_path, home_ip=home_ip)
    fake = runner or FakeRunner()
    bootstrap = HomeReleaseAuthorityBootstrap(
        source_root=ROOT,
        manifest_path=manifest,
        public_key_path=public_key,
        signer_identity="kolibri-owner",
        run_id="test-release-authority",
        root=root,
        backup_root=root / "var/backups/kolibri/release-authority",
        runner=fake,
        local_addresses=[f"{home_ip}/24"],
        owner_uid=os.geteuid(),
        owner_gid=os.getegid(),
        ssh_keygen=Path(shutil.which("ssh-keygen") or "/usr/bin/ssh-keygen"),
        systemctl=Path(shutil.which("true") or "/usr/bin/true"),
        runuser=Path(shutil.which("true") or "/usr/bin/true"),
    )
    return bootstrap, root, fake


def test_public_key_is_normalized_without_comment_or_body_disclosure(tmp_path):
    _manifest, public_key = write_inputs(tmp_path)

    signer = normalize_public_signer(public_key, "kolibri-owner")

    assert signer.allowed_signers_bytes.startswith(b"kolibri-owner ssh-ed25519 ")
    assert b"ignored-comment" not in signer.allowed_signers_bytes
    assert signer.digest.startswith("sha256:")


def test_private_key_material_is_rejected_before_any_apply(tmp_path):
    private = tmp_path / "not-public"
    private.write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\nredacted-test-material\n",
        encoding="ascii",
    )

    with pytest.raises(BootstrapError, match="signer_public_key_invalid"):
        normalize_public_signer(private, "kolibri-owner")


def test_default_plan_is_read_only_and_does_not_emit_public_key_body(tmp_path):
    bootstrap, root, _runner = bootstrap_for(tmp_path)

    result = bootstrap.plan()

    assert result["status"] == "planned"
    assert result["mode"] == "dry-run"
    assert result["target_node"] == "home"
    assert result["backend_release_dropin"] == "not_installed_by_this_bootstrap"
    assert PUBLIC_KEY_BODY.split()[1] not in json.dumps(result)
    assert not (root / "etc/kolibri").exists()
    assert not (root / "opt/kolibri-ai").exists()


def test_streamable_remote_preflight_is_read_only_and_digest_bound(tmp_path):
    bootstrap, root, _runner = bootstrap_for(tmp_path)
    signer = normalize_public_signer(
        bootstrap.public_key_path, bootstrap.signer_identity
    )

    result = preflight(signer.digest, root=root)

    assert result["status"] == "read_only_preflight_ok"
    assert result["current_target"] == "absent"
    assert set(result["trust"].values()) == {"absent"}
    assert not (root / "etc/kolibri").exists()


def test_streamable_remote_preflight_rejects_unsafe_current(tmp_path):
    bootstrap, root, _runner = bootstrap_for(tmp_path)
    signer = normalize_public_signer(
        bootstrap.public_key_path, bootstrap.signer_identity
    )
    (root / "opt/kolibri-ai/releases").mkdir(parents=True)
    outside = root / "srv/outside"
    outside.mkdir(parents=True)
    (root / "opt/kolibri-ai/current").symlink_to(outside)

    with pytest.raises(PreflightError, match="release_current_link_unsafe"):
        preflight(signer.digest, root=root)


def test_apply_installs_public_trust_and_passes_prerequisite_gate(tmp_path):
    bootstrap, root, runner = bootstrap_for(tmp_path)
    release_root = root / "opt/kolibri-ai/releases"
    release_target = release_root / "release-a"
    release_target.mkdir(parents=True)
    payload = release_target / "app.bin"
    payload.write_bytes(b"content-must-not-change")
    before_digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    (root / "opt/kolibri-ai/current").symlink_to("releases/release-a")
    os.chmod(root / "opt/kolibri-ai", 0o775)
    os.chmod(release_root, 0o775)
    os.chmod(release_target, 0o775)

    result = bootstrap.apply()

    allowed = root / "etc/kolibri/release_allowed_signers"
    owner_allowed = root / "etc/kolibri/owner_allowed_signers"
    assert result["status"] == "applied"
    assert result["prerequisite_status"]["status"] == "available"
    assert allowed.read_text(encoding="ascii") == owner_allowed.read_text(encoding="ascii")
    assert allowed.read_text(encoding="ascii").startswith("kolibri-owner ssh-ed25519 ")
    assert stat.S_IMODE(allowed.stat().st_mode) == 0o600
    assert stat.S_IMODE((root / "var/lib/kolibri-release/artifacts").stat().st_mode) == 0o700
    assert stat.S_IMODE((root / "run/kolibri-release").stat().st_mode) == 0o755
    assert stat.S_IMODE((root / "opt/kolibri-ai").stat().st_mode) == 0o755
    assert stat.S_IMODE(release_root.stat().st_mode) == 0o755
    assert stat.S_IMODE(release_target.stat().st_mode) == 0o755
    assert hashlib.sha256(payload.read_bytes()).hexdigest() == before_digest
    backup = Path(result["backup_directory"])
    assert (backup / "opt-metadata.before.json").is_file()
    assert (backup / "opt-checksums.before.json").is_file()
    assert (backup / "opt-checksums.after.json").is_file()
    assert (backup / "transaction.success.json").is_file()
    assert runner.socket_active is True
    assert runner.service_active is True
    assert runner.socket_enabled is True


@pytest.mark.parametrize(
    ("failed_step", "expected_code"),
    [
        ("daemon_reload", "release_authority_daemon_reload_failed"),
        ("enable", "release_authority_enable_failed"),
        ("socket_restart", "release_authority_socket_restart_failed"),
        ("service_restart", "release_authority_service_restart_failed"),
        ("socket_active", "release_authority_socket_inactive"),
        ("service_active", "release_authority_service_inactive"),
    ],
)
def test_activation_systemd_steps_have_distinct_sanitized_errors(
    tmp_path, capsys, failed_step, expected_code
):
    runner = ActivationRunner(fail_step=failed_step)
    bootstrap, _root, _runner = bootstrap_for(tmp_path, runner=runner)

    with pytest.raises(BootstrapError, match=f"^{expected_code}$"):
        bootstrap._activate_units()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert all(check is False for _command, check in runner.calls)


def test_activation_socket_probe_failure_is_distinct_and_sanitized(tmp_path, capsys):
    runner = ActivationRunner(probe_returncode=24)
    bootstrap, _root, _runner = bootstrap_for(tmp_path, runner=runner)

    with pytest.raises(BootstrapError, match="^release_authority_socket_probe_failed$"):
        bootstrap._activate_units()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert all(check is False for _command, check in runner.calls)


def test_activation_probe_reports_unavailable_prerequisite_separately(tmp_path):
    runner = ActivationRunner(probe_returncode=23)
    bootstrap, _root, _runner = bootstrap_for(tmp_path, runner=runner)

    with pytest.raises(BootstrapError, match="^release_authority_prerequisite_gate_failed$"):
        bootstrap._activate_units()

    assert all(check is False for _command, check in runner.calls)


def test_current_target_escape_fails_before_trust_mutation(tmp_path):
    bootstrap, root, _runner = bootstrap_for(tmp_path)
    (root / "opt/kolibri-ai/releases").mkdir(parents=True)
    outside = root / "srv/outside-release"
    outside.mkdir(parents=True)
    (root / "opt/kolibri-ai/current").symlink_to(outside)

    with pytest.raises(BootstrapError, match="release_current_link_unsafe"):
        bootstrap.apply()

    assert not (root / "etc/kolibri/release_allowed_signers").exists()
    assert not (root / "var/lib/kolibri-release/artifacts").exists()


@pytest.mark.parametrize("symlink_name", ["kolibri-ai", "kolibri-ai/releases"])
def test_symlinked_release_root_is_rejected(tmp_path, symlink_name):
    bootstrap, root, _runner = bootstrap_for(tmp_path)
    outside = root / "srv/outside-release-root"
    outside.mkdir(parents=True)
    target = root / "opt" / symlink_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(outside)

    with pytest.raises(BootstrapError, match="release_root_unsafe"):
        bootstrap.apply()

    assert not (root / "etc/kolibri/release_allowed_signers").exists()


def test_existing_different_trust_fails_closed_instead_of_rotating(tmp_path):
    bootstrap, root, _runner = bootstrap_for(tmp_path)
    trust_dir = root / "etc/kolibri"
    trust_dir.mkdir()
    existing = trust_dir / "release_allowed_signers"
    existing.write_text("another-owner ssh-ed25519 public-value\n", encoding="ascii")

    with pytest.raises(BootstrapError, match="release_authority_existing_trust_conflict"):
        bootstrap.apply()

    assert existing.read_text(encoding="ascii").startswith("another-owner ")
    assert not (trust_dir / "owner_allowed_signers").exists()


def test_failure_after_install_restores_files_modes_and_systemd_state(tmp_path):
    runner = FakeRunner(fail_helper_probe=True)
    bootstrap, root, _runner = bootstrap_for(tmp_path, runner=runner)
    etc_kolibri = root / "etc/kolibri"
    etc_kolibri.mkdir()
    policy = etc_kolibri / "release-policy.json"
    policy.write_bytes(b"old-policy-sentinel")
    os.chmod(etc_kolibri, 0o750)
    os.chmod(policy, 0o640)

    with pytest.raises(BootstrapError) as failure:
        bootstrap.apply()

    assert failure.value.rollback == "rolled_back"
    assert policy.read_bytes() == b"old-policy-sentinel"
    assert stat.S_IMODE(policy.stat().st_mode) == 0o640
    assert stat.S_IMODE(etc_kolibri.stat().st_mode) == 0o750
    assert not (etc_kolibri / "release_allowed_signers").exists()
    assert not (etc_kolibri / "owner_allowed_signers").exists()
    assert not (root / "var/lib/kolibri-release").exists()
    assert not (root / "usr/local/lib/kolibri").exists()
    assert runner.socket_enabled is False
    assert runner.socket_active is False
    assert runner.service_active is False
    backup = root / "var/backups/kolibri/release-authority/test-release-authority"
    rollback = json.loads((backup / "transaction.rollback.json").read_text())
    assert rollback["status"] == "rolled_back"


def test_operator_wrapper_is_dynamic_dry_run_first_and_excludes_backend_dropin():
    script = (ROOT / "scripts/bootstrap-home-release-authority.sh").read_text(
        encoding="utf-8"
    )

    assert "APPLY=false" in script
    assert 'if [ "$APPLY" != true ]' in script
    assert "--signer-public-key" in script
    assert "--signer-identity" in script
    assert "ops/control_plane_endpoint.py" in script
    assert "ops/home_release_authority_preflight.py" in script
    assert '/usr/bin/python3 - "$SIGNER_DIGEST"' in script
    assert "--print-url --manifest" in script
    assert "KOLIBRI_FACTORY_CONTROL_URL" not in script
    assert "kolibri-backend-home-release.conf" not in script
    assert "not_installed_by_this_bootstrap" in script
    assert "owner_allowed_signers" not in script  # generated only by the remote helper
    assert "PRIVATE KEY" not in script
