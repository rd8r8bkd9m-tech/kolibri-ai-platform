#!/usr/bin/env python3
"""One-time, fail-closed Home release-authority bootstrap.

This program is copied to the Home node by the operator wrapper.  Planning is
the default.  ``--apply`` is the only mode that mutates the host, and every
managed path is backed up before the first trust or systemd change.

Only an OpenSSH *public* key is accepted.  The program never accepts a private
key option, never reads a key from the environment, and never emits key body
material in its JSON result.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence

try:
    from ops.control_plane_endpoint import (
        ControlPlaneEndpointError,
        _read_home_mesh_ip,
        assert_local_home_control_plane,
    )
    from ops.release_installer import (
        RELEASE_CAPABILITY,
        ReleaseInstaller,
        ReleaseInstallerConfig,
        load_release_policy,
    )
except ImportError:  # staged execution with this file beside dependencies
    from control_plane_endpoint import (  # type: ignore[no-redef]
        ControlPlaneEndpointError,
        _read_home_mesh_ip,
        assert_local_home_control_plane,
    )
    from release_installer import (  # type: ignore[no-redef]
        RELEASE_CAPABILITY,
        ReleaseInstaller,
        ReleaseInstallerConfig,
        load_release_policy,
    )


SCHEMA_VERSION = "kolibri.home-release-authority-bootstrap.v1"
SAFE_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9@._:+-]{0,127}")
SAFE_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}")
SUPPORTED_PUBLIC_KEY_TYPES = frozenset(
    {
        "ssh-ed25519",
        "sk-ssh-ed25519@openssh.com",
        "ecdsa-sha2-nistp256",
        "ecdsa-sha2-nistp384",
        "ecdsa-sha2-nistp521",
        "sk-ecdsa-sha2-nistp256@openssh.com",
        "ssh-rsa",
    }
)
MAX_PUBLIC_KEY_BYTES = 32 * 1024
MAX_SOURCE_BYTES = 4 * 1024 * 1024

REQUIRED_SOURCES = {
    "ops/release_authority.py": "/usr/local/lib/kolibri/release_authority.py",
    "ops/release_helper.py": "/usr/local/lib/kolibri/release_helper.py",
    "ops/release_installer.py": "/usr/local/lib/kolibri/release_installer.py",
    "ops/release-policy.home.json": "/etc/kolibri/release-policy.json",
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
    # The socket itself is 0660/root:kolibri-agent.  Its parent must remain
    # traversable by that user even when it was created by an older 0750 unit.
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

SERVICE_UNIT = "kolibri-release-helper.service"
SOCKET_UNIT = "kolibri-release-helper.socket"


class BootstrapError(RuntimeError):
    """Sanitized bootstrap failure safe to include in operator evidence."""

    def __init__(self, code: str, *, rollback: str | None = None):
        super().__init__(code)
        self.code = code
        self.rollback = rollback


class CommandRunner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        check: bool = True,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess[str]: ...


class SubprocessCommandRunner:
    """Run fixed argv while keeping command output out of bootstrap logs."""

    def run(
        self,
        argv: Sequence[str],
        *,
        check: bool = True,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                [str(item) for item in argv],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise BootstrapError("release_authority_command_unavailable") from exc
        if check and completed.returncode != 0:
            raise BootstrapError("release_authority_command_failed")
        return completed


@dataclass(frozen=True)
class PublicSigner:
    identity: str
    algorithm: str
    encoded_key: str
    allowed_signers_bytes: bytes
    digest: str


@dataclass(frozen=True)
class PathRecord:
    path: str
    existed: bool
    kind: str | None = None
    mode: int | None = None
    uid: int | None = None
    gid: int | None = None
    backup_relative: str | None = None


@dataclass(frozen=True)
class SystemdState:
    socket_enabled: str
    socket_active: bool
    service_active: bool


def _rooted(root: Path, absolute_path: str | Path) -> Path:
    path = Path(absolute_path)
    if not path.is_absolute():
        raise BootstrapError("release_authority_path_invalid")
    return root / path.relative_to("/")


def _read_regular(path: Path, *, max_bytes: int, code: str) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_size <= 0
                or before.st_size > max_bytes
            ):
                raise BootstrapError(code)
            raw = handle.read(max_bytes + 1)
            after = os.fstat(handle.fileno())
        if (
            len(raw) > max_bytes
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise BootstrapError(code)
        return raw
    except BootstrapError:
        raise
    except OSError as exc:
        raise BootstrapError(code) from exc


def _decode_ssh_string(blob: bytes, offset: int = 0) -> tuple[bytes, int]:
    if len(blob) - offset < 4:
        raise BootstrapError("signer_public_key_invalid")
    size = int.from_bytes(blob[offset : offset + 4], "big")
    start = offset + 4
    end = start + size
    if size <= 0 or end > len(blob):
        raise BootstrapError("signer_public_key_invalid")
    return blob[start:end], end


def normalize_public_signer(path: Path, identity: str) -> PublicSigner:
    """Return one normalized allowed-signers row without exposing key body."""

    if not SAFE_IDENTITY.fullmatch(identity):
        raise BootstrapError("signer_identity_invalid")
    raw = _read_regular(
        path,
        max_bytes=MAX_PUBLIC_KEY_BYTES,
        code="signer_public_key_invalid",
    )
    if b"\x00" in raw or b"PRIVATE KEY" in raw.upper():
        raise BootstrapError("signer_public_key_invalid")
    try:
        text = raw.decode("ascii")
    except UnicodeError as exc:
        raise BootstrapError("signer_public_key_invalid") from exc
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise BootstrapError("signer_public_key_invalid")
    fields = lines[0].split()
    if len(fields) < 2 or fields[0] not in SUPPORTED_PUBLIC_KEY_TYPES:
        raise BootstrapError("signer_public_key_invalid")
    algorithm, encoded = fields[0], fields[1]
    try:
        blob = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise BootstrapError("signer_public_key_invalid") from exc
    embedded_algorithm, offset = _decode_ssh_string(blob)
    try:
        embedded_name = embedded_algorithm.decode("ascii")
    except UnicodeError as exc:
        raise BootstrapError("signer_public_key_invalid") from exc
    if embedded_name != algorithm or offset >= len(blob):
        raise BootstrapError("signer_public_key_invalid")
    normalized = f"{identity} {algorithm} {encoded}\n".encode("ascii")
    return PublicSigner(
        identity=identity,
        algorithm=algorithm,
        encoded_key=encoded,
        allowed_signers_bytes=normalized,
        digest=f"sha256:{hashlib.sha256(normalized).hexdigest()}",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise BootstrapError("release_authority_inventory_unsafe")
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
            after = os.fstat(handle.fileno())
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise BootstrapError("release_authority_inventory_changed")
    except BootstrapError:
        raise
    except OSError as exc:
        raise BootstrapError("release_authority_inventory_unavailable") from exc
    return f"sha256:{digest.hexdigest()}"


def _inventory_tree(path: Path) -> dict[str, Any]:
    """Capture metadata/checksums with descriptor-relative no-follow walks."""

    if not os.path.lexists(path):
        return {"exists": False, "entries": [], "checksums": {}}
    try:
        root_descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise BootstrapError("release_authority_inventory_unavailable") from exc

    entries: list[dict[str, Any]] = []
    checksums: dict[str, str] = {}

    def unchanged(before: os.stat_result, after: os.stat_result) -> bool:
        return (
            before.st_dev == after.st_dev
            and before.st_ino == after.st_ino
            and before.st_mode == after.st_mode
            and before.st_size == after.st_size
            and before.st_mtime_ns == after.st_mtime_ns
        )

    def file_digest(directory_descriptor: int, name: str, expected: os.stat_result) -> str:
        try:
            descriptor = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_descriptor,
            )
        except OSError as exc:
            raise BootstrapError("release_authority_inventory_unavailable") from exc
        digest = hashlib.sha256()
        try:
            with os.fdopen(descriptor, "rb") as handle:
                before = os.fstat(handle.fileno())
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_nlink != 1
                    or not unchanged(expected, before)
                ):
                    raise BootstrapError("release_authority_inventory_unsafe")
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                after = os.fstat(handle.fileno())
            if not unchanged(before, after):
                raise BootstrapError("release_authority_inventory_changed")
        except BootstrapError:
            raise
        except OSError as exc:
            raise BootstrapError("release_authority_inventory_unavailable") from exc
        return f"sha256:{digest.hexdigest()}"

    def walk(directory_descriptor: int, relative: str, depth: int) -> None:
        if depth > 128:
            raise BootstrapError("release_authority_inventory_unsafe")
        before = os.fstat(directory_descriptor)
        if not stat.S_ISDIR(before.st_mode):
            raise BootstrapError("release_authority_inventory_unsafe")
        entries.append(
            {
                "path": relative,
                "kind": "directory",
                "mode": stat.S_IMODE(before.st_mode),
                "uid": before.st_uid,
                "gid": before.st_gid,
                "size": before.st_size,
                "mtime_ns": before.st_mtime_ns,
            }
        )
        try:
            with os.scandir(directory_descriptor) as iterator:
                names = sorted(entry.name for entry in iterator)
        except OSError as exc:
            raise BootstrapError("release_authority_inventory_unavailable") from exc
        for name in names:
            if name in {"", ".", ".."} or "/" in name or "\x00" in name:
                raise BootstrapError("release_authority_inventory_unsafe")
            try:
                value = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
            except OSError as exc:
                raise BootstrapError("release_authority_inventory_unavailable") from exc
            child_relative = name if relative == "." else f"{relative}/{name}"
            if stat.S_ISDIR(value.st_mode):
                kind = "directory"
            elif stat.S_ISREG(value.st_mode):
                kind = "file"
            elif stat.S_ISLNK(value.st_mode):
                kind = "symlink"
            else:
                kind = "special"
            if kind != "directory":
                record: dict[str, Any] = {
                    "path": child_relative,
                    "kind": kind,
                    "mode": stat.S_IMODE(value.st_mode),
                    "uid": value.st_uid,
                    "gid": value.st_gid,
                    "size": value.st_size,
                    "mtime_ns": value.st_mtime_ns,
                }
                if kind == "symlink":
                    try:
                        record["target"] = os.readlink(
                            name, dir_fd=directory_descriptor
                        )
                    except OSError as exc:
                        raise BootstrapError(
                            "release_authority_inventory_unavailable"
                        ) from exc
                elif kind == "file":
                    checksums[child_relative] = file_digest(
                        directory_descriptor, name, value
                    )
                entries.append(record)
                continue
            try:
                child_descriptor = os.open(
                    name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_descriptor,
                )
            except OSError as exc:
                raise BootstrapError("release_authority_inventory_unavailable") from exc
            try:
                if not unchanged(value, os.fstat(child_descriptor)):
                    raise BootstrapError("release_authority_inventory_changed")
                walk(child_descriptor, child_relative, depth + 1)
            finally:
                os.close(child_descriptor)
        if not unchanged(before, os.fstat(directory_descriptor)):
            raise BootstrapError("release_authority_inventory_changed")

    try:
        walk(root_descriptor, ".", 0)
        return {
            "exists": True,
            "entries": sorted(entries, key=lambda item: item["path"]),
            "checksums": dict(sorted(checksums.items())),
        }
    finally:
        os.close(root_descriptor)


def _metadata(path: Path, logical: str) -> PathRecord:
    if not os.path.lexists(path):
        return PathRecord(path=logical, existed=False)
    try:
        value = path.lstat()
    except OSError as exc:
        raise BootstrapError("release_authority_backup_failed") from exc
    if stat.S_ISREG(value.st_mode):
        kind = "file"
    elif stat.S_ISDIR(value.st_mode):
        kind = "directory"
    else:
        raise BootstrapError("release_authority_managed_path_unsafe")
    return PathRecord(
        path=logical,
        existed=True,
        kind=kind,
        mode=stat.S_IMODE(value.st_mode),
        uid=value.st_uid,
        gid=value.st_gid,
    )


def _required_parent_is_safe(
    logical: str,
    value: os.stat_result,
    *,
    production_root: bool,
) -> bool:
    if not stat.S_ISDIR(value.st_mode):
        return False
    if not production_root:
        return True
    if value.st_uid != 0:
        return False
    mode = stat.S_IMODE(value.st_mode)
    if logical == "/run/lock":
        # Ubuntu commonly exposes the global lock directory as root-owned
        # 01777.  The sticky bit makes shared creation safe; accepting any
        # other writable shape here would weaken the bootstrap lock boundary.
        return mode == 0o1777
    return mode & 0o022 == 0


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(
    path: Path,
    payload: bytes,
    *,
    mode: int,
    uid: int,
    gid: int,
) -> None:
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            os.fchown(handle.fileno(), uid, gid)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        _fsync_directory(path.parent)
    except OSError as exc:
        raise BootstrapError("release_authority_file_install_failed") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


class HomeReleaseAuthorityBootstrap:
    def __init__(
        self,
        *,
        source_root: Path,
        manifest_path: Path,
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
    ):
        self.source_root = source_root.resolve()
        self.manifest_path = manifest_path.resolve()
        self.public_key_path = public_key_path.resolve()
        self.signer_identity = signer_identity
        self.run_id = run_id
        self.root = root.resolve()
        self.backup_root = backup_root or _rooted(
            self.root, "/var/backups/kolibri/release-authority"
        )
        self.runner = runner or SubprocessCommandRunner()
        self.local_addresses = list(local_addresses) if local_addresses is not None else None
        production_root = self.root == Path("/")
        self.owner_uid = 0 if owner_uid is None and production_root else (
            os.geteuid() if owner_uid is None else owner_uid
        )
        self.owner_gid = 0 if owner_gid is None and production_root else (
            os.getegid() if owner_gid is None else owner_gid
        )
        self.ssh_keygen = ssh_keygen or Path(shutil.which("ssh-keygen") or "/usr/bin/ssh-keygen")
        self.systemctl = systemctl or Path(shutil.which("systemctl") or "/usr/bin/systemctl")
        self.runuser = runuser or Path(shutil.which("runuser") or "/usr/sbin/runuser")
        self.ip_command = ip_command or Path(shutil.which("ip") or "/usr/sbin/ip")
        self.signer: PublicSigner | None = None
        self.home_mesh_ip: str | None = None
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

    def _validate_source_bundle(self) -> None:
        payloads: dict[str, bytes] = {}
        for relative in REQUIRED_SOURCES:
            source = self.source_root / relative
            payloads[relative] = _read_regular(
                source,
                max_bytes=MAX_SOURCE_BYTES,
                code="release_authority_source_invalid",
            )
        for relative in (
            "ops/release_authority.py",
            "ops/release_helper.py",
            "ops/release_installer.py",
        ):
            try:
                compile(payloads[relative], relative, "exec")
            except (SyntaxError, ValueError) as exc:
                raise BootstrapError("release_authority_source_invalid") from exc
        try:
            policy = load_release_policy(self.source_root / "ops/release-policy.home.json")
        except Exception as exc:
            raise BootstrapError("release_authority_policy_invalid") from exc
        if policy.services != frozenset({"kolibri-backend.service"}):
            raise BootstrapError("release_authority_policy_invalid")

        try:
            service = payloads["ops/systemd/kolibri-release-helper.service"].decode(
                "utf-8", errors="strict"
            )
            socket_unit = payloads["ops/systemd/kolibri-release-helper.socket"].decode(
                "utf-8", errors="strict"
            )
        except UnicodeError as exc:
            raise BootstrapError("release_authority_unit_invalid") from exc
        required_service_fragments = (
            "User=root",
            "KOLIBRI_ARTIFACT_ROOT=/var/lib/kolibri-release/artifacts",
            "KOLIBRI_RELEASE_ALLOWED_SIGNERS=/etc/kolibri/release_allowed_signers",
            "KOLIBRI_OWNER_APPROVAL_ALLOWED_SIGNERS=/etc/kolibri/owner_allowed_signers",
            "KOLIBRI_RELEASE_POLICY=/etc/kolibri/release-policy.json",
            "ExecStart=/usr/bin/python3 /usr/local/lib/kolibri/release_helper.py --serve-systemd",
        )
        required_socket_fragments = (
            "ListenStream=/run/kolibri-release/installer.sock",
            "SocketGroup=kolibri-agent",
            "SocketMode=0660",
            "DirectoryMode=0755",
        )
        if any(fragment not in service for fragment in required_service_fragments):
            raise BootstrapError("release_authority_unit_invalid")
        if any(fragment not in socket_unit for fragment in required_socket_fragments):
            raise BootstrapError("release_authority_unit_invalid")
        if "EnvironmentFile=" in service or "EnvironmentFile=" in socket_unit:
            raise BootstrapError("release_authority_unit_invalid")
        self.source_payloads = payloads

    def _validate_parent_directories(self) -> None:
        for logical in REQUIRED_PARENT_DIRECTORIES:
            path = self._path(logical)
            try:
                value = path.lstat()
            except OSError as exc:
                raise BootstrapError("release_authority_parent_unavailable") from exc
            if not _required_parent_is_safe(
                logical,
                value,
                production_root=self.root == Path("/"),
            ):
                raise BootstrapError("release_authority_parent_unsafe")

    def _validate_agent_identity(self) -> None:
        if self.root != Path("/"):
            return
        self.runner.run(["/usr/bin/id", "kolibri-agent"], check=True, timeout=5)

    def validate(self) -> None:
        if not SAFE_RUN_ID.fullmatch(self.run_id):
            raise BootstrapError("release_authority_run_id_invalid")
        self.signer = normalize_public_signer(self.public_key_path, self.signer_identity)
        key_probe = self.runner.run(
            [str(self.ssh_keygen), "-lf", str(self.public_key_path)],
            check=False,
            timeout=10,
        )
        if key_probe.returncode != 0:
            raise BootstrapError("signer_public_key_invalid")
        self._validate_source_bundle()
        self._validate_parent_directories()
        self._validate_agent_identity()
        try:
            self.home_mesh_ip = _read_home_mesh_ip(self.manifest_path)
            assert_local_home_control_plane(
                manifest_path=self.manifest_path,
                local_addresses=self._local_addresses(),
            )
        except ControlPlaneEndpointError as exc:
            raise BootstrapError("release_authority_target_not_home") from exc
        self._validate_existing_trust()
        self._validate_current_target()

    def _validate_existing_trust(self) -> None:
        assert self.signer is not None
        for logical in TRUST_DESTINATIONS:
            path = self._path(logical)
            if not os.path.lexists(path):
                continue
            existing = _read_regular(
                path,
                max_bytes=MAX_PUBLIC_KEY_BYTES,
                code="release_authority_existing_trust_unsafe",
            )
            if existing != self.signer.allowed_signers_bytes:
                raise BootstrapError("release_authority_existing_trust_conflict")

    def _validate_current_target(self) -> Path | None:
        base = self._path("/opt/kolibri-ai")
        releases = self._path("/opt/kolibri-ai/releases")
        current = self._path("/opt/kolibri-ai/current")
        for path in (base, releases):
            if os.path.lexists(path):
                try:
                    value = path.lstat()
                except OSError as exc:
                    raise BootstrapError("release_root_unsafe") from exc
                if not stat.S_ISDIR(value.st_mode):
                    raise BootstrapError("release_root_unsafe")
        if not os.path.lexists(current):
            return None
        if not current.is_symlink() or not os.path.lexists(releases):
            raise BootstrapError("release_current_link_unsafe")
        try:
            resolved_releases = releases.resolve(strict=True)
            resolved_target = current.resolve(strict=True)
        except OSError as exc:
            raise BootstrapError("release_current_link_unsafe") from exc
        if resolved_target.parent != resolved_releases or not resolved_target.is_dir():
            raise BootstrapError("release_current_link_unsafe")
        return resolved_target

    def plan(self) -> dict[str, Any]:
        self.validate()
        assert self.signer is not None
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "planned",
            "mode": "dry-run",
            "target_node": "home",
            "signer_identity": self.signer.identity,
            "signer_public_key_digest": self.signer.digest,
            "managed_paths": sorted(
                [*REQUIRED_SOURCES.values(), *TRUST_DESTINATIONS, *MANAGED_DIRECTORIES]
            ),
            "backend_release_dropin": "not_installed_by_this_bootstrap",
        }

    def _systemd_state(self) -> SystemdState:
        enabled = self.runner.run(
            [str(self.systemctl), "is-enabled", SOCKET_UNIT], check=False, timeout=10
        )
        active_socket = self.runner.run(
            [str(self.systemctl), "is-active", "--quiet", SOCKET_UNIT],
            check=False,
            timeout=10,
        )
        active_service = self.runner.run(
            [str(self.systemctl), "is-active", "--quiet", SERVICE_UNIT],
            check=False,
            timeout=10,
        )
        enabled_value = enabled.stdout.strip()
        if enabled_value not in {"enabled", "disabled", "static", "masked", "not-found"}:
            enabled_value = "enabled" if enabled.returncode == 0 else "disabled"
        return SystemdState(
            socket_enabled=enabled_value,
            socket_active=active_socket.returncode == 0,
            service_active=active_service.returncode == 0,
        )

    def _snapshot_managed_paths(self, backup: Path) -> list[PathRecord]:
        records: list[PathRecord] = []
        file_targets = [*REQUIRED_SOURCES.values(), *TRUST_DESTINATIONS]
        for logical in sorted(file_targets):
            path = self._path(logical)
            record = _metadata(path, logical)
            if record.existed and record.kind != "file":
                raise BootstrapError("release_authority_managed_path_unsafe")
            if record.existed:
                relative = logical.lstrip("/")
                destination = backup / "files" / relative
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                payload = _read_regular(
                    path,
                    max_bytes=MAX_SOURCE_BYTES,
                    code="release_authority_backup_failed",
                )
                _atomic_write(
                    destination,
                    payload,
                    mode=0o600,
                    uid=self.owner_uid,
                    gid=self.owner_gid,
                )
                record = PathRecord(
                    **{**record.__dict__, "backup_relative": f"files/{relative}"}
                )
            records.append(record)
        for logical in sorted(MANAGED_DIRECTORIES):
            record = _metadata(self._path(logical), logical)
            if record.existed and record.kind != "directory":
                raise BootstrapError("release_authority_managed_path_unsafe")
            records.append(record)
        return records

    def _write_backup_json(self, backup: Path, name: str, payload: Any) -> None:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        _atomic_write(
            backup / name,
            encoded,
            mode=0o600,
            uid=self.owner_uid,
            gid=self.owner_gid,
        )

    def _ensure_backup_root(self) -> None:
        base = self._path("/var/backups")
        candidate = self.backup_root.absolute()
        try:
            relative = candidate.relative_to(base.absolute())
        except ValueError as exc:
            raise BootstrapError("release_authority_backup_unavailable") from exc
        if not relative.parts:
            raise BootstrapError("release_authority_backup_unavailable")
        cursor = base
        for part in relative.parts:
            cursor = cursor / part
            try:
                if os.path.lexists(cursor):
                    value = cursor.lstat()
                    if (
                        not stat.S_ISDIR(value.st_mode)
                        or value.st_uid != self.owner_uid
                        or stat.S_IMODE(value.st_mode) & 0o022
                    ):
                        raise BootstrapError("release_authority_backup_unsafe")
                else:
                    cursor.mkdir(mode=0o700)
                    os.chown(cursor, self.owner_uid, self.owner_gid)
                    os.chmod(cursor, 0o700)
            except BootstrapError:
                raise
            except OSError as exc:
                raise BootstrapError("release_authority_backup_unavailable") from exc
        try:
            os.chown(candidate, self.owner_uid, self.owner_gid)
            os.chmod(candidate, 0o700)
        except OSError as exc:
            raise BootstrapError("release_authority_backup_unavailable") from exc

    def _prepare_backup(self) -> tuple[Path, list[PathRecord], dict[str, Any], SystemdState]:
        try:
            self._ensure_backup_root()
            backup = self.backup_root / self.run_id
            backup.mkdir(mode=0o700)
            os.chown(backup, self.owner_uid, self.owner_gid)
        except (FileExistsError, OSError) as exc:
            raise BootstrapError("release_authority_backup_unavailable") from exc

        records = self._snapshot_managed_paths(backup)
        # This inventory is intentionally captured before containment is used
        # to authorize any ownership/mode repair below /opt/kolibri-ai.
        opt_inventory = _inventory_tree(self._path("/opt/kolibri-ai"))
        systemd_state = self._systemd_state()
        self._write_backup_json(
            backup,
            "transaction.before.json",
            {
                "schema_version": SCHEMA_VERSION,
                "run_id": self.run_id,
                "status": "prepared",
                "managed_paths": [record.__dict__ for record in records],
                "systemd": systemd_state.__dict__,
            },
        )
        self._write_backup_json(backup, "opt-metadata.before.json", opt_inventory["entries"])
        self._write_backup_json(backup, "opt-checksums.before.json", opt_inventory["checksums"])
        return backup, records, opt_inventory, systemd_state

    def _ensure_directory(self, logical: str, mode: int) -> None:
        path = self._path(logical)
        try:
            if os.path.lexists(path):
                value = path.lstat()
                if not stat.S_ISDIR(value.st_mode):
                    raise BootstrapError("release_authority_managed_path_unsafe")
            else:
                path.mkdir(mode=mode)
            os.chown(path, self.owner_uid, self.owner_gid)
            os.chmod(path, mode)
        except BootstrapError:
            raise
        except OSError as exc:
            raise BootstrapError("release_authority_directory_install_failed") from exc

    def _install_files(self, current_target: Path | None) -> None:
        assert self.signer is not None
        for logical, mode in MANAGED_DIRECTORIES.items():
            self._ensure_directory(logical, mode)
        if current_target is not None:
            try:
                os.chown(current_target, self.owner_uid, self.owner_gid)
                os.chmod(current_target, 0o755)
            except OSError as exc:
                raise BootstrapError("release_authority_release_root_repair_failed") from exc

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

    def _installer_status(self) -> dict[str, Any]:
        installer = ReleaseInstaller(
            ReleaseInstallerConfig(
                artifact_root=self._path("/var/lib/kolibri-release/artifacts"),
                release_root=self._path("/opt/kolibri-ai/releases"),
                current_link=self._path("/opt/kolibri-ai/current"),
                allowed_signers=self._path("/etc/kolibri/release_allowed_signers"),
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
            raise BootstrapError("release_authority_prerequisite_gate_failed")
        return status

    def _activate_units(self) -> None:
        def fixed_step(
            argv: Sequence[str],
            *,
            error_code: str,
            timeout: int,
        ) -> subprocess.CompletedProcess[str]:
            try:
                completed = self.runner.run(argv, check=False, timeout=timeout)
            except BootstrapError as exc:
                raise BootstrapError(error_code) from exc
            if completed.returncode != 0:
                raise BootstrapError(error_code)
            return completed

        fixed_step(
            [str(self.systemctl), "daemon-reload"],
            error_code="release_authority_daemon_reload_failed",
            timeout=30,
        )
        fixed_step(
            [str(self.systemctl), "enable", SOCKET_UNIT],
            error_code="release_authority_enable_failed",
            timeout=30,
        )
        fixed_step(
            [str(self.systemctl), "restart", SOCKET_UNIT],
            error_code="release_authority_socket_restart_failed",
            timeout=30,
        )
        fixed_step(
            [str(self.systemctl), "restart", SERVICE_UNIT],
            error_code="release_authority_service_restart_failed",
            timeout=30,
        )
        fixed_step(
            [str(self.systemctl), "is-active", "--quiet", SOCKET_UNIT],
            error_code="release_authority_socket_inactive",
            timeout=10,
        )
        fixed_step(
            [str(self.systemctl), "is-active", "--quiet", SERVICE_UNIT],
            error_code="release_authority_service_inactive",
            timeout=10,
        )
        helper_probe = (
            "import sys;"
            "sys.path.insert(0,'/usr/local/lib/kolibri');"
            "from release_helper import ReleaseHelperClient;"
            "status=ReleaseHelperClient('/run/kolibri-release/installer.sock').prerequisite_status();"
            "reasons=status.get('reasons');"
            "transport={'release_helper_unavailable','release_task_heartbeat_failed'};"
            "prereq=status.get('status')=='unavailable' and isinstance(reasons,list) and bool(reasons) and not transport.intersection(reasons);"
            "raise SystemExit(0 if status.get('status')=='available' else 23 if prereq else 24)"
        )
        try:
            probe = self.runner.run(
                [
                    str(self.runuser),
                    "-u",
                    "kolibri-agent",
                    "--",
                    "/usr/bin/python3",
                    "-c",
                    helper_probe,
                ],
                check=False,
                timeout=20,
            )
        except BootstrapError as exc:
            raise BootstrapError("release_authority_socket_probe_failed") from exc
        if probe.returncode == 23:
            raise BootstrapError("release_authority_prerequisite_gate_failed")
        if probe.returncode != 0:
            raise BootstrapError("release_authority_socket_probe_failed")

    def _restore_systemd_state(self, state: SystemdState) -> list[str]:
        errors: list[str] = []

        def attempt(argv: Sequence[str], *, require_zero: bool = True) -> subprocess.CompletedProcess[str] | None:
            try:
                completed = self.runner.run(argv, check=False, timeout=30)
                if require_zero and completed.returncode != 0:
                    errors.append("systemd_restore_failed")
                return completed
            except BootstrapError:
                errors.append("systemd_restore_failed")
                return None

        attempt([str(self.systemctl), "daemon-reload"])
        if state.socket_enabled == "enabled":
            attempt([str(self.systemctl), "enable", SOCKET_UNIT])
        elif state.socket_enabled == "masked":
            attempt([str(self.systemctl), "mask", SOCKET_UNIT])
        elif state.socket_enabled == "disabled":
            attempt(
                [str(self.systemctl), "disable", SOCKET_UNIT], require_zero=False
            )
            enabled_probe = attempt(
                [str(self.systemctl), "is-enabled", SOCKET_UNIT], require_zero=False
            )
            if enabled_probe is not None and enabled_probe.stdout.strip() == "enabled":
                errors.append("systemd_restore_failed")
        if state.socket_active:
            attempt([str(self.systemctl), "start", SOCKET_UNIT])
        else:
            attempt([str(self.systemctl), "stop", SOCKET_UNIT], require_zero=False)
            active_probe = attempt(
                [str(self.systemctl), "is-active", "--quiet", SOCKET_UNIT],
                require_zero=False,
            )
            if active_probe is not None and active_probe.returncode == 0:
                errors.append("systemd_restore_failed")
        if state.service_active:
            attempt([str(self.systemctl), "start", SERVICE_UNIT])
        else:
            attempt([str(self.systemctl), "stop", SERVICE_UNIT], require_zero=False)
            active_probe = attempt(
                [str(self.systemctl), "is-active", "--quiet", SERVICE_UNIT],
                require_zero=False,
            )
            if active_probe is not None and active_probe.returncode == 0:
                errors.append("systemd_restore_failed")
        return errors

    def _rollback(
        self,
        backup: Path,
        records: list[PathRecord],
        opt_inventory: dict[str, Any],
        systemd_state: SystemdState,
    ) -> None:
        errors: list[str] = []
        for unit in (SERVICE_UNIT, SOCKET_UNIT):
            try:
                self.runner.run(
                    [str(self.systemctl), "stop", unit], check=False, timeout=30
                )
            except BootstrapError:
                errors.append("systemd_stop_failed")

        file_records = [record for record in records if record.path not in MANAGED_DIRECTORIES]
        for record in file_records:
            target = self._path(record.path)
            try:
                if record.existed:
                    if not record.backup_relative:
                        raise BootstrapError("release_authority_rollback_backup_missing")
                    payload = _read_regular(
                        backup / record.backup_relative,
                        max_bytes=MAX_SOURCE_BYTES,
                        code="release_authority_rollback_backup_missing",
                    )
                    _atomic_write(
                        target,
                        payload,
                        mode=int(record.mode),
                        uid=int(record.uid),
                        gid=int(record.gid),
                    )
                elif os.path.lexists(target):
                    target.unlink()
            except (BootstrapError, OSError):
                errors.append("file_restore_failed")

        before_by_path = {
            item["path"]: item for item in opt_inventory.get("entries", [])
        }
        trust_paths: list[Path] = [
            self._path("/opt/kolibri-ai"),
            self._path("/opt/kolibri-ai/releases"),
        ]
        current = self._path("/opt/kolibri-ai/current")
        if current.is_symlink():
            try:
                target = current.resolve(strict=True)
                trust_paths.append(target)
            except OSError:
                pass
        opt_root = self._path("/opt/kolibri-ai")
        for path in reversed(trust_paths):
            try:
                relative = "." if path == opt_root else path.relative_to(opt_root).as_posix()
                metadata = before_by_path.get(relative)
                if metadata and path.exists() and path.is_dir():
                    os.chown(path, int(metadata["uid"]), int(metadata["gid"]))
                    os.chmod(path, int(metadata["mode"]))
            except (OSError, ValueError):
                errors.append("trust_metadata_restore_failed")

        directory_records = [
            record for record in records if record.path in MANAGED_DIRECTORIES
        ]
        for record in sorted(
            directory_records,
            key=lambda item: len(Path(item.path).parts),
            reverse=True,
        ):
            target = self._path(record.path)
            try:
                if record.existed:
                    if not target.is_dir():
                        raise OSError("managed directory unavailable")
                    os.chown(target, int(record.uid), int(record.gid))
                    os.chmod(target, int(record.mode))
                elif target.exists():
                    target.rmdir()
            except OSError:
                errors.append("directory_restore_failed")

        errors.extend(self._restore_systemd_state(systemd_state))
        self._write_backup_json(
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
            raise BootstrapError("release_authority_rollback_failed")

    def apply(self) -> dict[str, Any]:
        self.validate()
        assert self.signer is not None
        if self.root == Path("/") and os.geteuid() != 0:
            raise BootstrapError("release_authority_apply_requires_root")

        lock_path = self._path("/run/lock/kolibri-release-authority-bootstrap.lock")
        try:
            lock_descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except OSError as exc:
            raise BootstrapError("release_authority_lock_unavailable") from exc
        with os.fdopen(lock_descriptor, "a+b") as lock_handle:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise BootstrapError("release_authority_lock_busy") from exc

            backup, records, opt_inventory, systemd_state = self._prepare_backup()
            try:
                # Containment is re-evaluated after the checksum/metadata backup
                # and immediately before /opt trust metadata may be changed.
                current_target = self._validate_current_target()
                self._install_files(current_target)
                after_inventory = _inventory_tree(self._path("/opt/kolibri-ai"))
                if after_inventory["checksums"] != opt_inventory["checksums"]:
                    raise BootstrapError("release_authority_content_changed")
                self._write_backup_json(
                    backup, "opt-checksums.after.json", after_inventory["checksums"]
                )
                prerequisite = self._installer_status()
                self._activate_units()
                self._write_backup_json(
                    backup,
                    "transaction.success.json",
                    {
                        "schema_version": SCHEMA_VERSION,
                        "run_id": self.run_id,
                        "status": "applied",
                        "signer_identity": self.signer.identity,
                        "signer_public_key_digest": self.signer.digest,
                        "prerequisite_status": prerequisite,
                    },
                )
            except BaseException as exc:
                code = exc.code if isinstance(exc, BootstrapError) else (
                    "release_authority_bootstrap_internal_error"
                )
                try:
                    self._rollback(backup, records, opt_inventory, systemd_state)
                except BootstrapError as rollback_exc:
                    raise BootstrapError(
                        code, rollback=rollback_exc.code
                    ) from rollback_exc
                raise BootstrapError(code, rollback="rolled_back") from exc

        return {
            "schema_version": SCHEMA_VERSION,
            "status": "applied",
            "mode": "apply",
            "target_node": "home",
            "run_id": self.run_id,
            "signer_identity": self.signer.identity,
            "signer_public_key_digest": self.signer.digest,
            "prerequisite_status": {
                "status": "available",
                "capability": RELEASE_CAPABILITY,
            },
            "backup_directory": str(backup),
            "backend_release_dropin": "not_installed_by_this_bootstrap",
        }


def _result_error(error: BootstrapError) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "failed",
        "error_code": error.code,
    }
    if error.rollback is not None:
        result["rollback"] = error.rollback
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--signer-public-key", required=True)
    parser.add_argument("--signer-identity", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    bootstrap = HomeReleaseAuthorityBootstrap(
        source_root=Path(args.source_root),
        manifest_path=Path(args.manifest),
        public_key_path=Path(args.signer_public_key),
        signer_identity=args.signer_identity,
        run_id=args.run_id,
    )
    try:
        result = bootstrap.apply() if args.apply else bootstrap.plan()
    except BootstrapError as exc:
        print(json.dumps(_result_error(exc), sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
