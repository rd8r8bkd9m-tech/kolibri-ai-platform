#!/usr/bin/env python3
"""Dynamic, worker-only compatibility bootstrap for signed runtime releases.

The fleet planner reads the replicated mesh manifest, excludes the logical
Home authority and derives deterministic ``1/2/3/5/rest`` waves from the
signed release digest.  The target bootstrap installs only public trust, the
privileged release helper, worker release policy and fixed health runtime.
It never installs or restarts Control Plane/backend services.

Planning is the default.  A target mutates its host only with ``--apply`` and
uses a checksum backup plus automatic rollback on any failed gate.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from ops.fleet_membership import MeshMembershipSource, MembershipError
    from ops.home_release_authority_bootstrap import (
        BootstrapError,
        CommandRunner,
        PathRecord,
        PublicSigner,
        SubprocessCommandRunner,
        SystemdState,
        _atomic_write,
        _inventory_tree,
        _metadata,
        _read_regular,
        _required_parent_is_safe,
        _rooted,
        normalize_public_signer,
    )
    from ops.release_installer import (
        RELEASE_CAPABILITY,
        ReleaseInstaller,
        ReleaseInstallerConfig,
        load_release_policy,
    )
except ImportError:  # staged execution beside dependencies
    from fleet_membership import MeshMembershipSource, MembershipError  # type: ignore[no-redef]
    from home_release_authority_bootstrap import (  # type: ignore[no-redef]
        BootstrapError,
        CommandRunner,
        PathRecord,
        PublicSigner,
        SubprocessCommandRunner,
        SystemdState,
        _atomic_write,
        _inventory_tree,
        _metadata,
        _read_regular,
        _required_parent_is_safe,
        _rooted,
        normalize_public_signer,
    )
    from release_installer import (  # type: ignore[no-redef]
        RELEASE_CAPABILITY,
        ReleaseInstaller,
        ReleaseInstallerConfig,
        load_release_policy,
    )


SCHEMA_VERSION = "kolibri.fleet-worker-release-authority-bootstrap.v1"
PLAN_SCHEMA_VERSION = "kolibri.fleet-worker-release-authority-plan.v1"
SAFE_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z")
SAFE_NODE_ID = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?\Z")
RELEASE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_PUBLIC_KEY_BYTES = 32 * 1024
SERVICE_UNIT = "kolibri-release-helper.service"
SOCKET_UNIT = "kolibri-release-helper.socket"

REQUIRED_SOURCES = {
    "ops/release_authority.py": "/usr/local/lib/kolibri/release_authority.py",
    "ops/release_helper.py": "/usr/local/lib/kolibri/release_helper.py",
    "ops/release_installer.py": "/usr/local/lib/kolibri/release_installer.py",
    "ops/worker_release_health.py": "/usr/local/lib/kolibri/worker_release_health.py",
    "ops/release-policy.worker.json": "/etc/kolibri/release-policy.json",
    "ops/systemd/kolibri-release-helper.service": (
        "/etc/systemd/system/kolibri-release-helper.service"
    ),
    "ops/systemd/kolibri-release-helper.socket": (
        "/etc/systemd/system/kolibri-release-helper.socket"
    ),
}
TRUST_DESTINATIONS = (
    "/etc/kolibri/release_allowed_signers",
    "/etc/kolibri/owner_allowed_signers",
)
MANAGED_DIRECTORIES = {
    "/usr/local/lib/kolibri": 0o755,
    "/etc/kolibri": 0o755,
    "/var/lib/kolibri-release": 0o700,
    "/var/lib/kolibri-release/artifacts": 0o700,
    "/opt/kolibri-ai": 0o755,
    "/opt/kolibri-ai/releases": 0o755,
    "/run/kolibri-release": 0o755,
}
REQUIRED_PARENT_DIRECTORIES = (
    "/usr/local/lib",
    "/etc",
    "/etc/systemd/system",
    "/var/lib",
    "/opt",
    "/var/backups",
    "/run/lock",
)


@dataclass(frozen=True)
class WorkerTarget:
    node_id: str
    mesh_ip: str


@dataclass(frozen=True)
class WorkerWave:
    name: str
    targets: tuple[WorkerTarget, ...]


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def plan_worker_waves(
    manifest_path: Path,
    release_digest: str,
    *,
    canary_only: bool = False,
) -> tuple[WorkerWave, ...]:
    """Return deterministic non-Home waves without a fixed fleet count."""

    if not RELEASE_DIGEST.fullmatch(release_digest):
        raise BootstrapError("worker_release_digest_invalid")
    try:
        snapshot = MeshMembershipSource(manifest_path).load()
    except MembershipError as exc:
        raise BootstrapError("worker_release_membership_invalid") from exc
    workers = [
        WorkerTarget(member.node_id, member.mesh_ip)
        for member in snapshot.members
        if member.node_id != "home"
    ]
    if not workers:
        raise BootstrapError("worker_release_membership_empty")
    workers.sort(
        key=lambda item: (
            hashlib.sha256(
                f"{release_digest}:{item.node_id}:{item.mesh_ip}".encode("utf-8")
            ).hexdigest(),
            item.node_id,
        )
    )
    sizes = (1, 2, 3, 5)
    names = ("canary", "wave-2", "wave-3", "wave-5")
    waves: list[WorkerWave] = []
    cursor = 0
    for name, size in zip(names, sizes, strict=True):
        selected = tuple(workers[cursor : cursor + size])
        if selected:
            waves.append(WorkerWave(name, selected))
        cursor += len(selected)
        if cursor == len(workers):
            break
    if cursor < len(workers):
        waves.append(WorkerWave("workers-rest", tuple(workers[cursor:])))
    if canary_only:
        return tuple(waves[:1])
    planned = [target.node_id for wave in waves for target in wave.targets]
    if len(planned) != len(workers) or len(planned) != len(set(planned)):
        raise BootstrapError("worker_release_plan_incomplete")
    return tuple(waves)


def plan_payload(
    manifest_path: Path,
    release_digest: str,
    *,
    canary_only: bool = False,
) -> dict[str, Any]:
    waves = plan_worker_waves(
        manifest_path,
        release_digest,
        canary_only=canary_only,
    )
    records = [
        {"node_id": target.node_id, "mesh_ip": target.mesh_ip}
        for wave in waves
        for target in wave.targets
    ]
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "status": "planned",
        "mode": "canary-only" if canary_only else "progressive",
        "membership_source": "replicated_mesh_manifest",
        "release_digest": release_digest,
        "membership_fingerprint": _canonical_hash(records),
        "selected_total": len(records),
        "waves": [
            {
                "name": wave.name,
                "nodes": [target.node_id for target in wave.targets],
            }
            for wave in waves
        ],
    }


def _file_checksums(paths: Iterable[tuple[str, Path]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for logical, path in paths:
        if not os.path.lexists(path):
            continue
        payload = _read_regular(
            path,
            max_bytes=MAX_SOURCE_BYTES,
            code="worker_release_checksum_failed",
        )
        result[logical] = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    return dict(sorted(result.items()))


class WorkerReleaseAuthorityBootstrap:
    """Transactional convergence of one manifest-selected worker."""

    def __init__(
        self,
        *,
        source_root: Path,
        manifest_path: Path,
        target_node: str,
        public_key_path: Path,
        signer_identity: str,
        run_id: str,
        root: Path = Path("/"),
        backup_root: Path | None = None,
        runner: CommandRunner | None = None,
        local_addresses: Iterable[str] | None = None,
        owner_uid: int | None = None,
        owner_gid: int | None = None,
        ssh_keygen: Path | None = None,
        systemctl: Path | None = None,
        runuser: Path | None = None,
        ip_command: Path | None = None,
    ) -> None:
        self.source_root = source_root.resolve()
        self.manifest_path = manifest_path.resolve()
        self.target_node = target_node
        self.public_key_path = public_key_path.resolve()
        self.signer_identity = signer_identity
        self.run_id = run_id
        self.root = root.resolve()
        self.backup_root = backup_root or _rooted(
            self.root, "/var/backups/kolibri/fleet-release-authority"
        )
        self.runner = runner or SubprocessCommandRunner()
        self.local_addresses = (
            list(local_addresses) if local_addresses is not None else None
        )
        production_root = self.root == Path("/")
        self.owner_uid = 0 if owner_uid is None and production_root else (
            os.geteuid() if owner_uid is None else owner_uid
        )
        self.owner_gid = 0 if owner_gid is None and production_root else (
            os.getegid() if owner_gid is None else owner_gid
        )
        self.ssh_keygen = ssh_keygen or Path(
            shutil.which("ssh-keygen") or "/usr/bin/ssh-keygen"
        )
        self.systemctl = systemctl or Path(
            shutil.which("systemctl") or "/usr/bin/systemctl"
        )
        self.runuser = runuser or Path(
            shutil.which("runuser") or "/usr/sbin/runuser"
        )
        self.ip_command = ip_command or Path(shutil.which("ip") or "/usr/sbin/ip")
        self.signer: PublicSigner | None = None
        self.target: WorkerTarget | None = None
        self.source_payloads: dict[str, bytes] = {}

    def _path(self, logical: str) -> Path:
        return _rooted(self.root, logical)

    def _local_addresses(self) -> list[str]:
        if self.local_addresses is not None:
            return self.local_addresses
        completed = self.runner.run(
            [str(self.ip_command), "-4", "-o", "addr", "show"],
            check=True,
            timeout=10,
        )
        return [
            field.split("/", 1)[0]
            for line in completed.stdout.splitlines()
            for field in line.split()
            if "/" in field
        ]

    def _validate_sources(self) -> None:
        payloads: dict[str, bytes] = {}
        for relative in REQUIRED_SOURCES:
            payloads[relative] = _read_regular(
                self.source_root / relative,
                max_bytes=MAX_SOURCE_BYTES,
                code="worker_release_source_invalid",
            )
        for relative in (
            "ops/release_authority.py",
            "ops/release_helper.py",
            "ops/release_installer.py",
            "ops/worker_release_health.py",
        ):
            try:
                compile(payloads[relative], relative, "exec")
            except (SyntaxError, ValueError) as exc:
                raise BootstrapError("worker_release_source_invalid") from exc
        try:
            policy = load_release_policy(
                self.source_root / "ops/release-policy.worker.json"
            )
        except Exception as exc:
            raise BootstrapError("worker_release_policy_invalid") from exc
        required = {
            "ops/agent_host.py",
            "ops/mimo/kolibri-response-only.md",
        }
        if (
            policy.services
            or policy.default_services
            or set(policy.required_payload_paths) != required
            or not policy.pre_health
            or not policy.pre_activate
            or not policy.post_health
        ):
            raise BootstrapError("worker_release_policy_invalid")
        try:
            service = payloads[
                "ops/systemd/kolibri-release-helper.service"
            ].decode("utf-8", errors="strict")
            socket = payloads[
                "ops/systemd/kolibri-release-helper.socket"
            ].decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise BootstrapError("worker_release_unit_invalid") from exc
        required_service = (
            "User=root",
            "KOLIBRI_RELEASE_POLICY=/etc/kolibri/release-policy.json",
            "ExecStart=/usr/bin/python3 -B /usr/local/lib/kolibri/release_helper.py --serve-systemd",
        )
        required_socket = (
            "ListenStream=/run/kolibri-release/installer.sock",
            "SocketGroup=kolibri-agent",
            "SocketMode=0660",
            "DirectoryMode=0755",
        )
        if (
            any(fragment not in service for fragment in required_service)
            or any(fragment not in socket for fragment in required_socket)
            or "EnvironmentFile=" in service
            or "EnvironmentFile=" in socket
            or "kolibri-backend" in service
            or "kolibri-factory-control" in service
        ):
            raise BootstrapError("worker_release_unit_invalid")
        self.source_payloads = payloads

    def _validate_parents(self) -> None:
        for logical in REQUIRED_PARENT_DIRECTORIES:
            try:
                value = self._path(logical).lstat()
            except OSError as exc:
                raise BootstrapError("worker_release_parent_unavailable") from exc
            if not _required_parent_is_safe(
                logical,
                value,
                production_root=self.root == Path("/"),
            ):
                raise BootstrapError("worker_release_parent_unsafe")

    def _validate_target(self) -> None:
        if not SAFE_NODE_ID.fullmatch(self.target_node) or self.target_node == "home":
            raise BootstrapError("worker_release_target_invalid")
        try:
            snapshot = MeshMembershipSource(self.manifest_path).load()
        except MembershipError as exc:
            raise BootstrapError("worker_release_membership_invalid") from exc
        member = snapshot.by_id.get(self.target_node)
        if member is None or member.node_id == "home":
            raise BootstrapError("worker_release_target_invalid")
        local = {item.split("/", 1)[0] for item in self._local_addresses()}
        if member.mesh_ip not in local:
            raise BootstrapError("worker_release_target_identity_mismatch")
        self.target = WorkerTarget(member.node_id, member.mesh_ip)

    def _validate_current(self) -> Path | None:
        base = self._path("/opt/kolibri-ai")
        releases = self._path("/opt/kolibri-ai/releases")
        current = self._path("/opt/kolibri-ai/current")
        for path in (base, releases):
            if os.path.lexists(path) and not stat.S_ISDIR(path.lstat().st_mode):
                raise BootstrapError("worker_release_root_unsafe")
        if not os.path.lexists(current):
            return None
        if not current.is_symlink() or not releases.is_dir():
            raise BootstrapError("worker_release_current_unsafe")
        try:
            selected = current.resolve(strict=True)
            release_root = releases.resolve(strict=True)
        except OSError as exc:
            raise BootstrapError("worker_release_current_unsafe") from exc
        if selected.parent != release_root or not selected.is_dir():
            raise BootstrapError("worker_release_current_unsafe")
        return selected

    def _validate_trust(self) -> None:
        assert self.signer is not None
        for logical in TRUST_DESTINATIONS:
            path = self._path(logical)
            if not os.path.lexists(path):
                continue
            existing = _read_regular(
                path,
                max_bytes=MAX_PUBLIC_KEY_BYTES,
                code="worker_release_existing_trust_unsafe",
            )
            if existing != self.signer.allowed_signers_bytes:
                raise BootstrapError("worker_release_existing_trust_conflict")

    def validate(self) -> None:
        if not SAFE_RUN_ID.fullmatch(self.run_id):
            raise BootstrapError("worker_release_run_id_invalid")
        self.signer = normalize_public_signer(
            self.public_key_path,
            self.signer_identity,
        )
        probe = self.runner.run(
            [str(self.ssh_keygen), "-lf", str(self.public_key_path)],
            check=False,
            timeout=10,
        )
        if probe.returncode != 0:
            raise BootstrapError("signer_public_key_invalid")
        self._validate_sources()
        self._validate_parents()
        if self.root == Path("/"):
            self.runner.run(["/usr/bin/id", "kolibri-agent"], check=True, timeout=5)
        self._validate_target()
        self._validate_trust()
        self._validate_current()

    def _systemd_state(self) -> SystemdState:
        enabled = self.runner.run(
            [str(self.systemctl), "is-enabled", SOCKET_UNIT],
            check=False,
            timeout=10,
        )
        socket = self.runner.run(
            [str(self.systemctl), "is-active", "--quiet", SOCKET_UNIT],
            check=False,
            timeout=10,
        )
        service = self.runner.run(
            [str(self.systemctl), "is-active", "--quiet", SERVICE_UNIT],
            check=False,
            timeout=10,
        )
        enabled_value = enabled.stdout.strip()
        if enabled_value not in {"enabled", "disabled", "static", "masked", "not-found"}:
            enabled_value = "enabled" if enabled.returncode == 0 else "disabled"
        return SystemdState(
            socket_enabled=enabled_value,
            socket_active=socket.returncode == 0,
            service_active=service.returncode == 0,
        )

    def _installer_status(self) -> dict[str, Any]:
        installer = ReleaseInstaller(
            ReleaseInstallerConfig(
                artifact_root=self._path("/var/lib/kolibri-release/artifacts"),
                release_root=self._path("/opt/kolibri-ai/releases"),
                current_link=self._path("/opt/kolibri-ai/current"),
                allowed_signers=self._path(
                    "/etc/kolibri/release_allowed_signers"
                ),
                policy_path=self._path("/etc/kolibri/release-policy.json"),
                ssh_keygen=self.ssh_keygen,
                systemctl=self.systemctl,
                owner_allowed_signers=self._path(
                    "/etc/kolibri/owner_allowed_signers"
                ),
            )
        )
        status = installer.prerequisite_status()
        if status.get("status") != "available":
            raise BootstrapError("worker_release_prerequisite_gate_failed")
        return status

    def _probe_helper(self) -> None:
        source = (
            "import sys;sys.path.insert(0,'/usr/local/lib/kolibri');"
            "from release_helper import ReleaseHelperClient;"
            "s=ReleaseHelperClient('/run/kolibri-release/installer.sock').prerequisite_status();"
            "raise SystemExit(0 if s.get('status')=='available' else 23)"
        )
        completed = self.runner.run(
            [
                str(self.runuser),
                "-u",
                "kolibri-agent",
                "--",
                "/usr/bin/python3",
                "-c",
                source,
            ],
            check=False,
            timeout=20,
        )
        if completed.returncode != 0:
            raise BootstrapError("worker_release_helper_probe_failed")

    def _activate(self) -> None:
        steps = (
            ([str(self.systemctl), "daemon-reload"], "worker_release_daemon_reload_failed"),
            ([str(self.systemctl), "enable", SOCKET_UNIT], "worker_release_enable_failed"),
            ([str(self.systemctl), "restart", SOCKET_UNIT], "worker_release_socket_restart_failed"),
            ([str(self.systemctl), "restart", SERVICE_UNIT], "worker_release_helper_restart_failed"),
            ([str(self.systemctl), "is-active", "--quiet", SOCKET_UNIT], "worker_release_socket_inactive"),
            ([str(self.systemctl), "is-active", "--quiet", SERVICE_UNIT], "worker_release_helper_inactive"),
        )
        for argv, code in steps:
            completed = self.runner.run(argv, check=False, timeout=30)
            if completed.returncode != 0:
                raise BootstrapError(code)
        self._probe_helper()

    def _is_converged(self) -> bool:
        assert self.signer is not None
        try:
            for relative, logical in REQUIRED_SOURCES.items():
                if _read_regular(
                    self._path(logical),
                    max_bytes=MAX_SOURCE_BYTES,
                    code="worker_release_not_converged",
                ) != self.source_payloads[relative]:
                    return False
            for logical in TRUST_DESTINATIONS:
                if _read_regular(
                    self._path(logical),
                    max_bytes=MAX_PUBLIC_KEY_BYTES,
                    code="worker_release_not_converged",
                ) != self.signer.allowed_signers_bytes:
                    return False
            for logical, mode in MANAGED_DIRECTORIES.items():
                value = self._path(logical).lstat()
                if not stat.S_ISDIR(value.st_mode) or stat.S_IMODE(value.st_mode) != mode:
                    return False
            state = self._systemd_state()
            if not (
                state.socket_enabled == "enabled"
                and state.socket_active
                and state.service_active
            ):
                return False
            self._installer_status()
            self._probe_helper()
        except (BootstrapError, OSError):
            return False
        return True

    def plan(self) -> dict[str, Any]:
        self.validate()
        assert self.signer is not None and self.target is not None
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "already_applied" if self._is_converged() else "planned",
            "mode": "dry-run",
            "target_node": self.target.node_id,
            "signer_identity": self.signer.identity,
            "signer_public_key_digest": self.signer.digest,
            "services": [],
            "control_plane_restart": False,
            "backend_restart": False,
        }

    def _ensure_directory(self, logical: str, mode: int) -> None:
        path = self._path(logical)
        try:
            if os.path.lexists(path):
                if not stat.S_ISDIR(path.lstat().st_mode):
                    raise BootstrapError("worker_release_managed_path_unsafe")
            else:
                path.mkdir(mode=mode)
            os.chown(path, self.owner_uid, self.owner_gid)
            os.chmod(path, mode)
        except BootstrapError:
            raise
        except OSError as exc:
            raise BootstrapError("worker_release_directory_install_failed") from exc

    def _ensure_backup_root(self) -> None:
        base = self._path("/var/backups")
        try:
            relative = self.backup_root.relative_to(base)
        except ValueError as exc:
            raise BootstrapError("worker_release_backup_unavailable") from exc
        if not relative.parts:
            raise BootstrapError("worker_release_backup_unavailable")
        cursor = base
        for part in relative.parts:
            cursor /= part
            try:
                if os.path.lexists(cursor):
                    value = cursor.lstat()
                    if (
                        not stat.S_ISDIR(value.st_mode)
                        or value.st_uid != self.owner_uid
                        or stat.S_IMODE(value.st_mode) & 0o022
                    ):
                        raise BootstrapError("worker_release_backup_unsafe")
                else:
                    cursor.mkdir(mode=0o700)
                    os.chown(cursor, self.owner_uid, self.owner_gid)
                os.chmod(cursor, 0o700)
            except BootstrapError:
                raise
            except OSError as exc:
                raise BootstrapError("worker_release_backup_unavailable") from exc

    def _write_json(self, backup: Path, name: str, payload: Any) -> None:
        _atomic_write(
            backup / name,
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
            mode=0o600,
            uid=self.owner_uid,
            gid=self.owner_gid,
        )

    def _snapshot(self, backup: Path) -> tuple[list[PathRecord], SystemdState, dict[str, Any]]:
        records: list[PathRecord] = []
        for logical in sorted([*REQUIRED_SOURCES.values(), *TRUST_DESTINATIONS]):
            path = self._path(logical)
            record = _metadata(path, logical)
            if record.existed and record.kind != "file":
                raise BootstrapError("worker_release_managed_path_unsafe")
            if record.existed:
                relative = logical.lstrip("/")
                destination = backup / "files" / relative
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                _atomic_write(
                    destination,
                    _read_regular(
                        path,
                        max_bytes=MAX_SOURCE_BYTES,
                        code="worker_release_backup_failed",
                    ),
                    mode=0o600,
                    uid=self.owner_uid,
                    gid=self.owner_gid,
                )
                record = PathRecord(
                    **{
                        **record.__dict__,
                        "backup_relative": f"files/{relative}",
                    }
                )
            records.append(record)
        for logical in sorted(MANAGED_DIRECTORIES):
            record = _metadata(self._path(logical), logical)
            if record.existed and record.kind != "directory":
                raise BootstrapError("worker_release_managed_path_unsafe")
            records.append(record)
        state = self._systemd_state()
        opt_inventory = _inventory_tree(self._path("/opt/kolibri-ai"))
        paths = [
            (logical, self._path(logical))
            for logical in [*REQUIRED_SOURCES.values(), *TRUST_DESTINATIONS]
        ]
        self._write_json(backup, "managed-checksums.before.json", _file_checksums(paths))
        self._write_json(backup, "opt-checksums.before.json", opt_inventory["checksums"])
        self._write_json(
            backup,
            "transaction.before.json",
            {
                "schema_version": SCHEMA_VERSION,
                "run_id": self.run_id,
                "target_node": self.target_node,
                "status": "prepared",
                "managed_paths": [record.__dict__ for record in records],
                "systemd": state.__dict__,
            },
        )
        return records, state, opt_inventory

    def _install(self, current_target: Path | None) -> None:
        assert self.signer is not None
        for logical, mode in MANAGED_DIRECTORIES.items():
            self._ensure_directory(logical, mode)
        if current_target is not None:
            os.chown(current_target, self.owner_uid, self.owner_gid)
            os.chmod(current_target, 0o755)
        for relative, logical in REQUIRED_SOURCES.items():
            _atomic_write(
                self._path(logical),
                self.source_payloads[relative],
                mode=0o644,
                uid=self.owner_uid,
                gid=self.owner_gid,
            )
        for logical in TRUST_DESTINATIONS:
            _atomic_write(
                self._path(logical),
                self.signer.allowed_signers_bytes,
                mode=0o600,
                uid=self.owner_uid,
                gid=self.owner_gid,
            )

    def _restore_systemd(self, state: SystemdState) -> list[str]:
        errors: list[str] = []

        def run(argv: Sequence[str], *, require_zero: bool = True) -> None:
            try:
                completed = self.runner.run(argv, check=False, timeout=30)
                if require_zero and completed.returncode != 0:
                    errors.append("systemd_restore_failed")
            except BootstrapError:
                errors.append("systemd_restore_failed")

        run([str(self.systemctl), "daemon-reload"])
        if state.socket_enabled == "enabled":
            run([str(self.systemctl), "enable", SOCKET_UNIT])
        elif state.socket_enabled == "masked":
            run([str(self.systemctl), "mask", SOCKET_UNIT])
        else:
            run([str(self.systemctl), "disable", SOCKET_UNIT], require_zero=False)
        run(
            [
                str(self.systemctl),
                "start" if state.socket_active else "stop",
                SOCKET_UNIT,
            ],
            require_zero=state.socket_active,
        )
        run(
            [
                str(self.systemctl),
                "start" if state.service_active else "stop",
                SERVICE_UNIT,
            ],
            require_zero=state.service_active,
        )
        return errors

    def _rollback(
        self,
        backup: Path,
        records: list[PathRecord],
        state: SystemdState,
    ) -> None:
        errors: list[str] = []
        for unit in (SERVICE_UNIT, SOCKET_UNIT):
            try:
                self.runner.run(
                    [str(self.systemctl), "stop", unit],
                    check=False,
                    timeout=30,
                )
            except BootstrapError:
                errors.append("systemd_stop_failed")
        file_records = [
            item for item in records if item.path not in MANAGED_DIRECTORIES
        ]
        for record in file_records:
            target = self._path(record.path)
            try:
                if record.existed:
                    if not record.backup_relative:
                        raise BootstrapError("worker_release_backup_missing")
                    _atomic_write(
                        target,
                        _read_regular(
                            backup / record.backup_relative,
                            max_bytes=MAX_SOURCE_BYTES,
                            code="worker_release_backup_missing",
                        ),
                        mode=int(record.mode),
                        uid=int(record.uid),
                        gid=int(record.gid),
                    )
                elif os.path.lexists(target):
                    target.unlink()
            except (BootstrapError, OSError):
                errors.append("file_restore_failed")
        for record in sorted(
            (item for item in records if item.path in MANAGED_DIRECTORIES),
            key=lambda item: len(Path(item.path).parts),
            reverse=True,
        ):
            target = self._path(record.path)
            try:
                if record.existed:
                    os.chown(target, int(record.uid), int(record.gid))
                    os.chmod(target, int(record.mode))
                elif target.exists():
                    target.rmdir()
            except OSError:
                errors.append("directory_restore_failed")
        errors.extend(self._restore_systemd(state))
        self._write_json(
            backup,
            "transaction.rollback.json",
            {
                "schema_version": SCHEMA_VERSION,
                "run_id": self.run_id,
                "status": "rollback_failed" if errors else "rolled_back",
                "errors": sorted(set(errors)),
            },
        )
        if errors:
            raise BootstrapError("worker_release_rollback_failed")

    def apply(self) -> dict[str, Any]:
        self.validate()
        assert self.signer is not None and self.target is not None
        if self.root == Path("/") and os.geteuid() != 0:
            raise BootstrapError("worker_release_apply_requires_root")
        if self._is_converged():
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "already_applied",
                "mode": "apply",
                "target_node": self.target.node_id,
                "services": [],
                "control_plane_restart": False,
                "backend_restart": False,
            }
        lock = self._path("/run/lock/kolibri-worker-release-authority.lock")
        try:
            descriptor = os.open(
                lock,
                os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except OSError as exc:
            raise BootstrapError("worker_release_lock_unavailable") from exc
        with os.fdopen(descriptor, "a+b") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise BootstrapError("worker_release_lock_busy") from exc
            self._ensure_backup_root()
            backup = self.backup_root / self.run_id
            try:
                backup.mkdir(mode=0o700)
                os.chown(backup, self.owner_uid, self.owner_gid)
            except (FileExistsError, OSError) as exc:
                raise BootstrapError("worker_release_backup_unavailable") from exc
            records, state, opt_before = self._snapshot(backup)
            try:
                current_target = self._validate_current()
                self._install(current_target)
                opt_after = _inventory_tree(self._path("/opt/kolibri-ai"))
                if opt_after["checksums"] != opt_before["checksums"]:
                    raise BootstrapError("worker_release_content_changed")
                self._write_json(
                    backup,
                    "opt-checksums.after.json",
                    opt_after["checksums"],
                )
                paths = [
                    (logical, self._path(logical))
                    for logical in [*REQUIRED_SOURCES.values(), *TRUST_DESTINATIONS]
                ]
                self._write_json(
                    backup,
                    "managed-checksums.after.json",
                    _file_checksums(paths),
                )
                prerequisite = self._installer_status()
                self._activate()
                self._write_json(
                    backup,
                    "transaction.success.json",
                    {
                        "schema_version": SCHEMA_VERSION,
                        "run_id": self.run_id,
                        "target_node": self.target.node_id,
                        "status": "applied",
                        "signer_identity": self.signer.identity,
                        "signer_public_key_digest": self.signer.digest,
                        "prerequisite_status": prerequisite,
                    },
                )
            except BaseException as exc:
                code = (
                    exc.code
                    if isinstance(exc, BootstrapError)
                    else "worker_release_bootstrap_internal_error"
                )
                try:
                    self._rollback(backup, records, state)
                except BootstrapError as rollback_error:
                    raise BootstrapError(
                        code,
                        rollback=rollback_error.code,
                    ) from rollback_error
                raise BootstrapError(code, rollback="rolled_back") from exc
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "applied",
            "mode": "apply",
            "target_node": self.target.node_id,
            "run_id": self.run_id,
            "signer_identity": self.signer.identity,
            "signer_public_key_digest": self.signer.digest,
            "prerequisite_status": {
                "status": "available",
                "capability": RELEASE_CAPABILITY,
            },
            "backup_directory": str(backup),
            "services": [],
            "control_plane_restart": False,
            "backend_restart": False,
        }


def _target_result_error(error: BootstrapError) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "failed",
        "error_code": error.code,
    }
    if error.rollback is not None:
        result["rollback"] = error.rollback
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--manifest", required=True, type=Path)
    plan.add_argument("--release-digest", required=True)
    plan.add_argument("--canary-only", action="store_true")
    plan.add_argument("--format", choices=("json", "tsv"), default="json")

    target = commands.add_parser("target")
    target.add_argument("--source-root", required=True, type=Path)
    target.add_argument("--manifest", required=True, type=Path)
    target.add_argument("--target-node", required=True)
    target.add_argument("--signer-public-key", required=True, type=Path)
    target.add_argument("--signer-identity", required=True)
    target.add_argument("--run-id", required=True)
    target.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "plan":
            waves = plan_worker_waves(
                args.manifest,
                args.release_digest,
                canary_only=args.canary_only,
            )
            if args.format == "tsv":
                for wave in waves:
                    for target in wave.targets:
                        print(f"{wave.name}\t{target.node_id}\t{target.mesh_ip}")
            else:
                print(
                    json.dumps(
                        plan_payload(
                            args.manifest,
                            args.release_digest,
                            canary_only=args.canary_only,
                        ),
                        indent=2,
                        sort_keys=True,
                    )
                )
            return 0

        bootstrap = WorkerReleaseAuthorityBootstrap(
            source_root=args.source_root,
            manifest_path=args.manifest,
            target_node=args.target_node,
            public_key_path=args.signer_public_key,
            signer_identity=args.signer_identity,
            run_id=args.run_id,
        )
        result = bootstrap.apply() if args.apply else bootstrap.plan()
        print(json.dumps(result, sort_keys=True))
        return 0
    except BootstrapError as exc:
        print(json.dumps(_target_result_error(exc), sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
