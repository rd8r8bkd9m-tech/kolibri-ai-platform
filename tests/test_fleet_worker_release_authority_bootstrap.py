from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from ops.fleet_worker_release_authority_bootstrap import (
    BootstrapError,
    WorkerReleaseAuthorityBootstrap,
    plan_payload,
    plan_worker_waves,
)
from ops.release_installer import load_release_policy
from ops.worker_release_health import (
    WorkerReleaseHealthError,
    check_candidate,
    check_current,
    check_pre,
)


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_KEY = (
    "ssh-ed25519 "
    "AAAAC3NzaC1lZDI1NTE5AAAAIGFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFh"
)
RELEASE_DIGEST = "sha256:" + "a" * 64


class FakeRunner:
    def __init__(self, *, fail_probe: bool = False):
        self.fail_probe = fail_probe
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
            active = (
                self.socket_active
                if command[3].endswith(".socket")
                else self.service_active
            )
            returncode = 0 if active else 3
        elif len(command) >= 3 and command[1] in {"start", "restart", "stop"}:
            active = command[1] != "stop"
            if command[2].endswith(".socket"):
                self.socket_active = active
            else:
                self.service_active = active
        elif len(command) >= 3 and command[1] == "enable":
            self.socket_enabled = True
        elif len(command) >= 3 and command[1] in {"disable", "mask"}:
            self.socket_enabled = False
        elif "kolibri-agent" in command and "-c" in command:
            returncode = 24 if self.fail_probe else 0
        completed = subprocess.CompletedProcess(
            command,
            returncode,
            stdout=stdout,
            stderr="",
        )
        if check and returncode != 0:
            raise BootstrapError("worker_release_command_failed")
        return completed


def write_manifest(tmp_path: Path, workers: int = 12) -> Path:
    peers = {
        "10.77.0.1": {"node_id": "home", "mesh_ip": "10.77.0.1"},
    }
    for index in range(1, workers + 1):
        ip = f"10.77.0.{index + 1}"
        peers[ip] = {"node_id": f"worker-{index:02d}", "mesh_ip": ip}
    path = tmp_path / "peers.json"
    path.write_text(json.dumps({"peers": peers}), encoding="utf-8")
    return path


def prepare_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    for relative in (
        "usr/local/lib",
        "etc/systemd/system",
        "var/lib",
        "var/backups",
        "opt",
        "run/lock",
    ):
        (root / relative).mkdir(parents=True, mode=0o755)
    return root


def make_bootstrap(
    tmp_path: Path,
    *,
    runner: FakeRunner | None = None,
) -> tuple[WorkerReleaseAuthorityBootstrap, Path, FakeRunner]:
    root = prepare_root(tmp_path)
    manifest = write_manifest(tmp_path, workers=2)
    public = tmp_path / "signer.pub"
    public.write_text(f"{PUBLIC_KEY} test-comment\n", encoding="ascii")
    fake = runner or FakeRunner()
    bootstrap = WorkerReleaseAuthorityBootstrap(
        source_root=ROOT,
        manifest_path=manifest,
        target_node="worker-01",
        public_key_path=public,
        signer_identity="kolibri-owner",
        run_id="worker-bootstrap-test",
        root=root,
        runner=fake,
        local_addresses=["10.77.0.2/24"],
        owner_uid=os.geteuid(),
        owner_gid=os.getegid(),
        ssh_keygen=Path(shutil.which("ssh-keygen") or "/usr/bin/ssh-keygen"),
        systemctl=Path(shutil.which("true") or "/usr/bin/true"),
        runuser=Path(shutil.which("true") or "/usr/bin/true"),
    )
    return bootstrap, root, fake


def test_dynamic_plan_excludes_home_and_uses_digest_seeded_1_2_3_5_rest(tmp_path):
    manifest = write_manifest(tmp_path, workers=12)

    waves = plan_worker_waves(manifest, RELEASE_DIGEST)

    assert [len(wave.targets) for wave in waves] == [1, 2, 3, 5, 1]
    assert [wave.name for wave in waves] == [
        "canary",
        "wave-2",
        "wave-3",
        "wave-5",
        "workers-rest",
    ]
    nodes = [target.node_id for wave in waves for target in wave.targets]
    assert "home" not in nodes
    assert len(nodes) == len(set(nodes)) == 12
    assert plan_worker_waves(manifest, RELEASE_DIGEST) == waves


def test_canary_only_selects_digest_seeded_first_worker(tmp_path):
    manifest = write_manifest(tmp_path, workers=20)

    complete = plan_worker_waves(manifest, RELEASE_DIGEST)
    canary = plan_worker_waves(manifest, RELEASE_DIGEST, canary_only=True)
    payload = plan_payload(manifest, RELEASE_DIGEST, canary_only=True)

    assert canary == complete[:1]
    assert len(canary) == 1 and len(canary[0].targets) == 1
    assert payload["mode"] == "canary-only"
    assert payload["selected_total"] == 1


def test_worker_policy_has_no_service_and_requires_exact_runtime_pair():
    policy = load_release_policy(ROOT / "ops/release-policy.worker.json")

    assert policy.services == frozenset()
    assert policy.default_services == ()
    assert set(policy.required_payload_paths) == {
        "ops/agent_host.py",
        "ops/mimo/kolibri-response-only.md",
    }
    assert policy.pre_health and policy.pre_activate and policy.post_health
    assert all(check.argv[0] == "/usr/bin/python3" for check in policy.pre_health)


def test_default_target_plan_is_read_only(tmp_path):
    bootstrap, root, _runner = make_bootstrap(tmp_path)

    result = bootstrap.plan()

    assert result["status"] == "planned"
    assert result["mode"] == "dry-run"
    assert result["target_node"] == "worker-01"
    assert result["services"] == []
    assert result["control_plane_restart"] is False
    assert result["backend_restart"] is False
    assert not (root / "etc/kolibri").exists()
    assert not (root / "usr/local/lib/kolibri").exists()


def test_apply_installs_only_public_trust_helper_policy_and_is_idempotent(tmp_path):
    bootstrap, root, runner = make_bootstrap(tmp_path)
    release = root / "opt/kolibri-ai/releases/old-release"
    release.mkdir(parents=True)
    sentinel = release / "sentinel.bin"
    sentinel.write_bytes(b"must-not-change")
    before = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    (root / "opt/kolibri-ai/current").symlink_to("releases/old-release")

    result = bootstrap.apply()
    repeated = bootstrap.apply()

    assert result["status"] == "applied"
    assert repeated["status"] == "already_applied"
    assert (root / "etc/kolibri/release-policy.json").read_bytes() == (
        ROOT / "ops/release-policy.worker.json"
    ).read_bytes()
    allowed = root / "etc/kolibri/release_allowed_signers"
    owner = root / "etc/kolibri/owner_allowed_signers"
    assert allowed.read_bytes() == owner.read_bytes()
    assert b"test-comment" not in allowed.read_bytes()
    assert stat.S_IMODE(allowed.stat().st_mode) == 0o600
    assert not (root / "etc/systemd/system/kolibri-factory-control.service.d").exists()
    assert not (root / "etc/systemd/system/kolibri-backend.service.d").exists()
    assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == before
    backup = Path(result["backup_directory"])
    assert (backup / "managed-checksums.before.json").is_file()
    assert (backup / "managed-checksums.after.json").is_file()
    assert (backup / "transaction.success.json").is_file()
    assert runner.socket_enabled and runner.socket_active and runner.service_active


def test_failed_helper_probe_restores_prior_policy_and_units(tmp_path):
    runner = FakeRunner(fail_probe=True)
    bootstrap, root, _runner = make_bootstrap(tmp_path, runner=runner)
    prior = root / "etc/kolibri/release-policy.json"
    prior.parent.mkdir(parents=True)
    prior.write_bytes(b"prior-policy")
    os.chmod(prior, 0o640)

    with pytest.raises(BootstrapError) as failure:
        bootstrap.apply()

    assert failure.value.rollback == "rolled_back"
    assert prior.read_bytes() == b"prior-policy"
    assert stat.S_IMODE(prior.stat().st_mode) == 0o640
    assert not (root / "etc/kolibri/release_allowed_signers").exists()
    assert not (root / "etc/kolibri/owner_allowed_signers").exists()
    assert runner.socket_enabled is False
    assert runner.socket_active is False
    assert runner.service_active is False


def test_health_checks_validate_candidate_and_atomic_current(tmp_path):
    release_root = tmp_path / "releases"
    release = release_root / "candidate-a"
    (release / "ops/mimo").mkdir(parents=True)
    runtime = release / "ops/agent_host.py"
    runtime.write_text("#!/usr/bin/python3\n", encoding="utf-8")
    os.chmod(runtime, 0o755)
    profile = release / "ops/mimo/kolibri-response-only.md"
    profile.write_text("profile\n", encoding="utf-8")
    current = tmp_path / "current"
    current.symlink_to(release)

    check_candidate(
        release_dir=release,
        release_root=release_root,
        owner_uid=os.geteuid(),
    )
    check_current(
        release_dir=release,
        release_root=release_root,
        current_link=current,
        owner_uid=os.geteuid(),
    )
    os.chmod(runtime, 0o777)
    with pytest.raises(WorkerReleaseHealthError, match="worker_release_payload_unsafe"):
        check_candidate(
            release_dir=release,
            release_root=release_root,
            owner_uid=os.geteuid(),
        )


def test_pre_health_accepts_contained_historical_product_only_release(tmp_path):
    release_root = tmp_path / "releases"
    historical = release_root / "historical-product"
    historical.mkdir(parents=True)
    (historical / "frontend.bin").write_bytes(b"legacy-product-only")
    current = tmp_path / "current"
    current.symlink_to(historical)

    check_pre(
        release_root=release_root,
        current_link=current,
        owner_uid=os.geteuid(),
    )


def test_wrapper_is_dynamic_dry_run_first_and_never_mentions_legacy_canary():
    script = (
        ROOT / "scripts/bootstrap-fleet-worker-release-authority.sh"
    ).read_text(encoding="utf-8")

    assert "APPLY=false" in script
    assert 'if [ "$APPLY" != true ]' in script
    assert "--canary-only" in script
    assert "--release-digest" in script
    assert "fleet_worker_release_authority_bootstrap.py" in script
    assert "worker_release_authority_preflight.py" in script
    assert "EXPECTED=" not in script
    assert "CANARY=" not in script
    assert "agent09" not in script
    assert "StrictHostKeyChecking=no" not in script
    assert "ops/telegram.env" not in script
    assert "kolibri-factory-control.service" not in script
    assert "kolibri-backend.service" not in script
