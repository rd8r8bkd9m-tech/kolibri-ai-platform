#!/usr/bin/env python3
"""One-time, node-local Agent Host compatibility bootstrap.

This is the explicit transition barrier for workers whose bootstrap
``/usr/local/bin/kolibri-agent-host`` predates immutable runtime re-exec and
long-task heartbeats.  It intentionally contains no remote transport: an
owner-controlled operator must stage the public source bundle and invoke this
program locally as root on each node in the approved wave.

Default operation is read-only.  ``--apply`` is required for either an install
or rollback.  The tool never writes runner access, Agent Host environment,
mesh membership, provider credentials, backend, or Control Plane state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

try:
    from ops.control_plane_endpoint import resolve_home_control_plane_url
    from ops.fleet_membership import MembershipError, MeshMembershipSource
except ImportError:  # installed standalone beside the Agent Host modules
    from control_plane_endpoint import resolve_home_control_plane_url
    from fleet_membership import MembershipError, MeshMembershipSource


SCHEMA_VERSION = "kolibri.agent-host-compat-bootstrap.v1"
PLAN_SCHEMA_VERSION = "kolibri.agent-host-compat-plan.v1"
PROOF_SCHEMA_VERSION = "kolibri.agent-host-compat-proof.v1"
LONG_PROBE_KIND = "lease_heartbeat_probe"
RELEASE_CAPABILITY = "release_apply_v1"
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z")
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
DEFAULT_MINIMUM_WORKERS = 20
WAVE_LAYOUT = (
    ("compat-canary", 1),
    ("compat-workers-2", 2),
    ("compat-workers-3", 3),
    ("compat-workers-5", 5),
)
PRESERVED_PATHS = (
    "/etc/kolibri-agent-host.env",
    "/etc/kolibri/runner-access.json",
    "/var/lib/kolibri-mesh/peers.json",
)


@dataclass(frozen=True)
class InstallRecord:
    source: str
    destination: str
    mode: int


INSTALL_RECORDS = (
    InstallRecord("ops/agent_host.py", "/usr/local/bin/kolibri-agent-host", 0o755),
    InstallRecord(
        "ops/mimo/kolibri-response-only.md",
        "/usr/local/lib/kolibri/mimo/kolibri-response-only.md",
        0o644,
    ),
    InstallRecord(
        "ops/control_plane_endpoint.py",
        "/usr/local/lib/kolibri/control_plane_endpoint.py",
        0o644,
    ),
    InstallRecord("ops/runner_access.py", "/usr/local/lib/kolibri/runner_access.py", 0o644),
    InstallRecord(
        "ops/release_authority.py",
        "/usr/local/lib/kolibri/release_authority.py",
        0o644,
    ),
    InstallRecord("ops/release_helper.py", "/usr/local/lib/kolibri/release_helper.py", 0o644),
    InstallRecord(
        "ops/release_installer.py",
        "/usr/local/lib/kolibri/release_installer.py",
        0o644,
    ),
    InstallRecord(
        "ops/systemd/kolibri-agent-host.service",
        "/etc/systemd/system/kolibri-agent-host.service",
        0o644,
    ),
)


class BootstrapError(RuntimeError):
    """Stable failure boundary safe to place in operator evidence."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    def run(
        self,
        command: list[str],
        *,
        check: bool = False,
        timeout: int | float = 30,
    ) -> CommandResult: ...


class SubprocessCommandRunner:
    def run(
        self,
        command: list[str],
        *,
        check: bool = False,
        timeout: int | float = 30,
    ) -> CommandResult:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        result = CommandResult(completed.returncode, completed.stdout, completed.stderr)
        if check and result.returncode != 0:
            raise BootstrapError("agent_host_compat_command_failed")
        return result


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise BootstrapError("agent_host_compat_evidence_invalid") from exc


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: Any) -> str:
    return _digest_bytes(_canonical_json_bytes(value))


def _rooted(root: Path, logical: str) -> Path:
    if not logical.startswith("/") or ".." in Path(logical).parts:
        raise BootstrapError("agent_host_compat_path_invalid")
    return root / logical.lstrip("/")


def _read_regular(path: Path, *, max_bytes: int = 32 * 1024 * 1024) -> bytes:
    try:
        value = path.lstat()
        if (
            not stat.S_ISREG(value.st_mode)
            or stat.S_ISLNK(value.st_mode)
            or value.st_nlink != 1
            or value.st_size <= 0
            or value.st_size > max_bytes
            or stat.S_IMODE(value.st_mode) & 0o022
        ):
            raise BootstrapError("agent_host_compat_source_unsafe")
        return path.read_bytes()
    except BootstrapError:
        raise
    except OSError as exc:
        raise BootstrapError("agent_host_compat_source_unavailable") from exc


def _path_digest(path: Path) -> str | None:
    if not os.path.lexists(path):
        return None
    return _digest_bytes(_read_regular(path))


def load_source_payloads(source_root: Path) -> dict[str, bytes]:
    payloads = {
        record.source: _read_regular(source_root / record.source)
        for record in INSTALL_RECORDS
    }
    for record in INSTALL_RECORDS:
        if record.source.endswith(".py"):
            try:
                compile(payloads[record.source], record.source, "exec")
            except (SyntaxError, ValueError) as exc:
                raise BootstrapError("agent_host_compat_python_invalid") from exc
    agent_source = payloads["ops/agent_host.py"].decode("utf-8", errors="strict")
    service = payloads["ops/systemd/kolibri-agent-host.service"].decode(
        "utf-8", errors="strict"
    )
    profile_digest = hashlib.sha256(
        payloads["ops/mimo/kolibri-response-only.md"]
    ).hexdigest()
    required_agent_fragments = (
        "LEASE_HEARTBEAT_PROBE_KIND",
        "maybe_reexec_release_agent_host()",
        f'MIMO_RESPONSE_PROFILE_SHA256 = "{profile_digest}"',
    )
    required_service_fragments = (
        "EnvironmentFile=/etc/kolibri-agent-host.env",
        "ExecStart=/usr/bin/python3 -B /usr/local/bin/kolibri-agent-host",
        "Environment=PYTHONPATH=/usr/local/lib/kolibri",
        "Environment=PYTHONDONTWRITEBYTECODE=1",
    )
    if any(fragment not in agent_source for fragment in required_agent_fragments):
        raise BootstrapError("agent_host_compat_runtime_contract_invalid")
    if any(fragment not in service for fragment in required_service_fragments):
        raise BootstrapError("agent_host_compat_unit_contract_invalid")
    if "KOLIBRI_FACTORY_CONTROL_URLS=" in service:
        raise BootstrapError("agent_host_compat_unit_contract_invalid")
    return payloads


def source_bundle_digest(payloads: dict[str, bytes]) -> str:
    records = [
        {
            "path": record.source,
            "destination": record.destination,
            "mode": f"{record.mode:04o}",
            "sha256": _digest_bytes(payloads[record.source]),
        }
        for record in INSTALL_RECORDS
    ]
    return _digest_json(records)


def compatibility_plan(
    *,
    source_root: Path,
    manifest_path: Path,
    minimum_workers: int = DEFAULT_MINIMUM_WORKERS,
    canary_only: bool = False,
) -> dict[str, Any]:
    if minimum_workers < 1:
        raise BootstrapError("agent_host_compat_minimum_workers_invalid")
    payloads = load_source_payloads(source_root)
    bundle_digest = source_bundle_digest(payloads)
    try:
        snapshot = MeshMembershipSource(manifest_path).load()
    except MembershipError as exc:
        raise BootstrapError(str(exc)) from exc
    workers = [member for member in snapshot.members if member.node_id != "home"]
    if len(workers) < minimum_workers:
        raise BootstrapError("agent_host_compat_worker_count_below_minimum")
    ordered = sorted(
        workers,
        key=lambda member: (
            hashlib.sha256(
                f"{bundle_digest}:{member.node_id}".encode("utf-8")
            ).hexdigest(),
            member.node_id,
        ),
    )
    waves: list[dict[str, Any]] = []
    offset = 0
    for name, size in WAVE_LAYOUT:
        selected = ordered[offset : offset + size]
        offset += len(selected)
        if selected:
            waves.append({"name": name, "nodes": [item.node_id for item in selected]})
    if offset < len(ordered):
        waves.append(
            {"name": "compat-workers-rest", "nodes": [item.node_id for item in ordered[offset:]]}
        )
    if canary_only:
        waves = waves[:1]
    material = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "source_bundle_digest": bundle_digest,
        "membership_digest": f"sha256:{snapshot.digest}",
        "membership_epoch": snapshot.epoch,
        "home_excluded": True,
        "minimum_workers": minimum_workers,
        "canonical_worker_total": len(workers),
        "selected_worker_total": sum(len(wave["nodes"]) for wave in waves),
        "canary_only": canary_only,
        "waves": waves,
    }
    return {**material, "plan_digest": _digest_json(material), "mode": "dry-run"}


def _atomic_write(path: Path, payload: bytes, *, mode: int, uid: int, gid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    except OSError as exc:
        raise BootstrapError("agent_host_compat_install_failed") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class NodeBootstrap:
    def __init__(
        self,
        *,
        source_root: Path,
        manifest_path: Path,
        node_id: str,
        run_id: str,
        approved_plan_digest: str | None = None,
        root: Path = Path("/"),
        backup_root: Path | None = None,
        runner: CommandRunner | None = None,
        local_addresses: Iterable[str] | None = None,
        owner_uid: int | None = None,
        owner_gid: int | None = None,
        stability_seconds: int = 15,
        canary_only: bool = False,
        minimum_workers: int = DEFAULT_MINIMUM_WORKERS,
    ):
        self.source_root = source_root.resolve()
        self.manifest_path = manifest_path.resolve()
        self.node_id = node_id
        self.run_id = run_id
        self.approved_plan_digest = approved_plan_digest
        self.root = root.resolve()
        self.backup_root = backup_root or _rooted(
            self.root, "/var/backups/kolibri/agent-host-compat"
        )
        self.runner = runner or SubprocessCommandRunner()
        self.local_addresses = list(local_addresses) if local_addresses is not None else None
        production = self.root == Path("/")
        self.owner_uid = 0 if owner_uid is None and production else (
            os.geteuid() if owner_uid is None else owner_uid
        )
        self.owner_gid = 0 if owner_gid is None and production else (
            os.getegid() if owner_gid is None else owner_gid
        )
        self.stability_seconds = stability_seconds
        self.canary_only = canary_only
        self.minimum_workers = minimum_workers
        self.payloads: dict[str, bytes] = {}
        self.plan_value: dict[str, Any] = {}

    @property
    def backup_dir(self) -> Path:
        return self.backup_root / self.run_id / self.node_id

    def _path(self, logical: str) -> Path:
        return _rooted(self.root, logical)

    def _observed_addresses(self) -> list[str]:
        if self.local_addresses is not None:
            return [str(value).split("/", 1)[0] for value in self.local_addresses]
        result = self.runner.run(
            ["/usr/sbin/ip", "-4", "-o", "addr", "show"],
            check=True,
            timeout=10,
        )
        return [
            field.split("/", 1)[0]
            for line in result.stdout.splitlines()
            for field in line.split()
            if "/" in field
        ]

    def validate(self) -> None:
        if not SAFE_ID.fullmatch(self.node_id) or self.node_id == "home":
            raise BootstrapError("agent_host_compat_node_invalid")
        if not SAFE_ID.fullmatch(self.run_id):
            raise BootstrapError("agent_host_compat_run_id_invalid")
        if self.approved_plan_digest is not None and not SHA256.fullmatch(
            self.approved_plan_digest
        ):
            raise BootstrapError("agent_host_compat_plan_digest_invalid")
        if self.root == Path("/") and os.geteuid() != 0:
            raise BootstrapError("agent_host_compat_root_required")
        self.payloads = load_source_payloads(self.source_root)
        self.plan_value = compatibility_plan(
            source_root=self.source_root,
            manifest_path=self.manifest_path,
            canary_only=self.canary_only,
            minimum_workers=self.minimum_workers,
        )
        if (
            self.approved_plan_digest is not None
            and self.plan_value["plan_digest"] != self.approved_plan_digest
        ):
            raise BootstrapError("agent_host_compat_plan_changed")
        try:
            snapshot = MeshMembershipSource(self.manifest_path).load()
        except MembershipError as exc:
            raise BootstrapError(str(exc)) from exc
        member = snapshot.by_id.get(self.node_id)
        if member is None or member.mesh_ip not in set(self._observed_addresses()):
            raise BootstrapError("agent_host_compat_target_identity_mismatch")
        selected_nodes = {
            selected
            for wave in self.plan_value["waves"]
            for selected in wave["nodes"]
        }
        if self.node_id not in selected_nodes:
            raise BootstrapError("agent_host_compat_node_not_in_approved_plan")
        for preserved in PRESERVED_PATHS:
            path = self._path(preserved)
            if not os.path.lexists(path):
                raise BootstrapError("agent_host_compat_preserved_path_missing")
            _read_regular(path, max_bytes=2 * 1024 * 1024)

    def _checksums(self) -> dict[str, str | None]:
        return {
            record.destination: _path_digest(self._path(record.destination))
            for record in INSTALL_RECORDS
        }

    def _preserved_checksums(self) -> dict[str, str | None]:
        return {path: _path_digest(self._path(path)) for path in PRESERVED_PATHS}

    def _desired_checksums(self) -> dict[str, str]:
        return {
            record.destination: _digest_bytes(self.payloads[record.source])
            for record in INSTALL_RECORDS
        }

    def _service_active(self) -> bool:
        return self._systemctl(
            "is-active", "--quiet", "kolibri-agent-host.service", check=False
        ).returncode == 0

    def plan(self) -> dict[str, Any]:
        self.validate()
        current = self._checksums()
        desired = self._desired_checksums()
        service_active = self._service_active()
        return {
            "schema_version": SCHEMA_VERSION,
            "status": (
                "already_converged"
                if current == desired and service_active
                else "planned"
            ),
            "mode": "dry-run",
            "node_id": self.node_id,
            "run_id": self.run_id,
            "plan_digest": self.plan_value["plan_digest"],
            "source_bundle_digest": self.plan_value["source_bundle_digest"],
            "membership_digest": self.plan_value["membership_digest"],
            "changed_paths": sorted(path for path in desired if current.get(path) != desired[path]),
            "service_active": service_active,
            "preserved_paths": list(PRESERVED_PATHS),
            "service_restart_scope": ["kolibri-agent-host.service"],
        }

    def _write_json(self, path: Path, value: Any) -> None:
        _atomic_write(
            path,
            _canonical_json_bytes(value) + b"\n",
            mode=0o600,
            uid=self.owner_uid,
            gid=self.owner_gid,
        )

    def _capture_backup(self, before: dict[str, str | None], preserved: dict[str, str | None]) -> None:
        if self.backup_dir.exists():
            raise BootstrapError("agent_host_compat_backup_exists")
        self.backup_dir.mkdir(parents=True, mode=0o700)
        files_dir = self.backup_dir / "files"
        files_dir.mkdir(mode=0o700)
        for record in INSTALL_RECORDS:
            source = self._path(record.destination)
            if before[record.destination] is None:
                continue
            target = files_dir / record.destination.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target, follow_symlinks=False)
        self._write_json(self.backup_dir / "checksums.before.json", before)
        self._write_json(self.backup_dir / "preserved.before.json", preserved)
        self._write_json(
            self.backup_dir / "metadata.json",
            {
                "schema_version": SCHEMA_VERSION,
                "node_id": self.node_id,
                "run_id": self.run_id,
                "plan_digest": self.plan_value["plan_digest"],
                "source_bundle_digest": self.plan_value["source_bundle_digest"],
            },
        )

    def _systemctl(self, *arguments: str, check: bool = True) -> CommandResult:
        return self.runner.run(
            ["/usr/bin/systemctl", *arguments],
            check=check,
            timeout=30,
        )

    def _restart_and_verify(self) -> dict[str, Any]:
        self._systemctl("daemon-reload")
        self._systemctl("enable", "kolibri-agent-host.service")
        before = self._systemctl(
            "show", "kolibri-agent-host.service", "-p", "NRestarts", "--value"
        ).stdout.strip()
        self._systemctl("restart", "kolibri-agent-host.service")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self._systemctl(
                "is-active", "--quiet", "kolibri-agent-host.service", check=False
            ).returncode == 0:
                break
            time.sleep(1)
        else:
            raise BootstrapError("agent_host_compat_service_inactive")
        stable_start = self._systemctl(
            "show", "kolibri-agent-host.service", "-p", "NRestarts", "--value"
        ).stdout.strip()
        time.sleep(self.stability_seconds)
        if self._systemctl(
            "is-active", "--quiet", "kolibri-agent-host.service", check=False
        ).returncode != 0:
            raise BootstrapError("agent_host_compat_service_inactive")
        stable_end = self._systemctl(
            "show", "kolibri-agent-host.service", "-p", "NRestarts", "--value"
        ).stdout.strip()
        if not stable_start.isdigit() or stable_start != stable_end:
            raise BootstrapError("agent_host_compat_restart_storm_detected")
        return {
            "nrestarts_before": int(before) if before.isdigit() else None,
            "nrestarts_stable": int(stable_end),
            "stability_seconds": self.stability_seconds,
        }

    def apply(self) -> dict[str, Any]:
        planned = self.plan()
        if self.approved_plan_digest is None:
            raise BootstrapError("agent_host_compat_approved_plan_required")
        if planned["status"] == "already_converged":
            return {**planned, "mode": "apply", "status": "already_converged", "restarted": False}
        before = self._checksums()
        preserved = self._preserved_checksums()
        self._capture_backup(before, preserved)
        try:
            for record in INSTALL_RECORDS:
                _atomic_write(
                    self._path(record.destination),
                    self.payloads[record.source],
                    mode=record.mode,
                    uid=self.owner_uid,
                    gid=self.owner_gid,
                )
            after = self._checksums()
            if after != self._desired_checksums():
                raise BootstrapError("agent_host_compat_checksum_mismatch")
            if self._preserved_checksums() != preserved:
                raise BootstrapError("agent_host_compat_preserved_path_changed")
            service = self._restart_and_verify()
            self._write_json(self.backup_dir / "checksums.after.json", after)
            self._write_json(self.backup_dir / "preserved.after.json", preserved)
            self._write_json(self.backup_dir / "status.json", {"status": "applied"})
            return {
                **planned,
                "mode": "apply",
                "status": "applied",
                "restarted": True,
                "backup_dir": str(self.backup_dir),
                "service": service,
            }
        except Exception:
            self.rollback(skip_validate=True)
            raise

    def rollback(self, *, skip_validate: bool = False) -> dict[str, Any]:
        if not skip_validate:
            if not SAFE_ID.fullmatch(self.node_id) or self.node_id == "home":
                raise BootstrapError("agent_host_compat_node_invalid")
            if not SAFE_ID.fullmatch(self.run_id):
                raise BootstrapError("agent_host_compat_run_id_invalid")
            if self.root == Path("/") and os.geteuid() != 0:
                raise BootstrapError("agent_host_compat_root_required")
        metadata_path = self.backup_dir / "metadata.json"
        before_path = self.backup_dir / "checksums.before.json"
        if not metadata_path.is_file() or not before_path.is_file():
            raise BootstrapError("agent_host_compat_backup_missing")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        before = json.loads(before_path.read_text(encoding="utf-8"))
        if metadata.get("node_id") != self.node_id or metadata.get("run_id") != self.run_id:
            raise BootstrapError("agent_host_compat_backup_identity_invalid")
        if (
            self.approved_plan_digest is not None
            and metadata.get("plan_digest") != self.approved_plan_digest
        ):
            raise BootstrapError("agent_host_compat_backup_plan_mismatch")
        if self._checksums() == before and self._service_active():
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "already_rolled_back",
                "node_id": self.node_id,
                "run_id": self.run_id,
            }
        files_dir = self.backup_dir / "files"
        for record in INSTALL_RECORDS:
            destination = self._path(record.destination)
            expected = before.get(record.destination)
            backup = files_dir / record.destination.lstrip("/")
            if expected is None:
                destination.unlink(missing_ok=True)
                continue
            payload = _read_regular(backup)
            _atomic_write(
                destination,
                payload,
                mode=stat.S_IMODE(backup.stat().st_mode),
                uid=self.owner_uid,
                gid=self.owner_gid,
            )
        if self._checksums() != before:
            raise BootstrapError("agent_host_compat_rollback_checksum_mismatch")
        service = self._restart_and_verify()
        self._write_json(self.backup_dir / "status.json", {"status": "rolled_back"})
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "rolled_back",
            "node_id": self.node_id,
            "run_id": self.run_id,
            "service": service,
        }


class ControlPlaneClient:
    def __init__(self, base_url: str, *, timeout_seconds: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = None if payload is None else _canonical_json_bytes(payload)
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, urllib.error.HTTPError) as exc:
            raise BootstrapError("agent_host_compat_control_plane_request_failed") from exc


def submit_long_probe(
    *,
    client: ControlPlaneClient,
    node_id: str,
    campaign_id: str,
    duration_seconds: int = 65,
    poll_seconds: float = 2.0,
) -> dict[str, Any]:
    if not SAFE_ID.fullmatch(node_id) or node_id == "home":
        raise BootstrapError("agent_host_compat_node_invalid")
    if not SAFE_ID.fullmatch(campaign_id):
        raise BootstrapError("agent_host_compat_campaign_id_invalid")
    if not 61 <= duration_seconds <= 180:
        raise BootstrapError("agent_host_compat_probe_duration_invalid")
    node = client.request("GET", f"/v1/nodes/{urllib.parse.quote(node_id, safe='')}")
    capabilities = node.get("capabilities") if isinstance(node, dict) else None
    if not isinstance(capabilities, list) or LONG_PROBE_KIND not in capabilities:
        return {
            "schema_version": PROOF_SCHEMA_VERSION,
            "status": "contract_not_supported",
            "node_id": node_id,
            "required_capability": LONG_PROBE_KIND,
        }
    submitted = client.request(
        "POST",
        "/v1/tasks",
        {
            "schema_version": PROOF_SCHEMA_VERSION,
            "idempotency_key": f"agent-host-compat:{campaign_id}:{node_id}",
            "kind": LONG_PROBE_KIND,
            "required_capability": LONG_PROBE_KIND,
            "target_node": node_id,
            "permission_pack": "read_only",
            "read_only": True,
            "no_push": True,
            "write_scope": [],
            "proof_duration_seconds": duration_seconds,
            "constraints": {"read_only": True, "max_wall_seconds": duration_seconds + 60},
            "max_attempts": 2,
        },
    )
    task_id = str(submitted.get("task_id") or "") if isinstance(submitted, dict) else ""
    if not task_id:
        raise BootstrapError("agent_host_compat_probe_submission_failed")
    deadline = time.monotonic() + duration_seconds + 120
    task: dict[str, Any] = {}
    while time.monotonic() < deadline:
        observed = client.request("GET", f"/v1/tasks/{urllib.parse.quote(task_id, safe='')}")
        if not isinstance(observed, dict):
            raise BootstrapError("agent_host_compat_probe_record_invalid")
        task = observed
        state = str(task.get("state") or "")
        if state in {"completed", "failed", "dead_letter", "cancelled"}:
            break
        time.sleep(poll_seconds)
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    proof = result.get("lease_heartbeat_probe") if isinstance(result, dict) else None
    lease_owner = str(task.get("lease_owner") or "")
    result_reference = str(task.get("result_reference") or "")
    checks = {
        "state": task.get("state") == "completed",
        "attempt": bool(
            str(task.get("attempt_id") or "")
            and result.get("attempt_id") == task.get("attempt_id")
        ),
        "fence": bool(
            type(task.get("fencing_token")) is int
            and task["fencing_token"] > 0
            and result.get("fencing_token") == task.get("fencing_token")
        ),
        "node": bool(
            lease_owner.startswith(f"{node_id}:") and result.get("node_id") == node_id
        ),
        "result_reference": bool(
            result_reference and result.get("result_path") == result_reference
        ),
        "duration": bool(
            isinstance(proof, dict)
            and float(proof.get("observed_duration_seconds") or 0) >= duration_seconds
            and int(proof.get("heartbeat_count") or 0) >= 2
        ),
    }
    verifier = task.get("completion_verifier")
    verifier_supported = isinstance(verifier, dict)
    if verifier_supported:
        checks["independent_verifier"] = bool(
            verifier.get("verdict") == "passed"
            and verifier.get("independent") is True
            and verifier.get("verifier") == "control-plane/home"
        )
    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "schema_version": PROOF_SCHEMA_VERSION,
        "status": "completed" if not failed else "failed",
        "node_id": node_id,
        "task_id": task_id,
        "attempt_id": task.get("attempt_id"),
        "fencing_token": task.get("fencing_token"),
        "result_reference": result_reference or None,
        "checks": checks,
        "failed_checks": failed,
        "strict_verifier_supported": verifier_supported,
        "release_apply_ready": RELEASE_CAPABILITY in capabilities,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--source-root", required=True)
    plan_parser.add_argument("--manifest", required=True)
    plan_parser.add_argument(
        "--minimum-workers", type=int, default=DEFAULT_MINIMUM_WORKERS
    )
    plan_parser.add_argument("--canary-only", action="store_true")

    for name in ("node", "rollback"):
        node_parser = subparsers.add_parser(name)
        node_parser.add_argument("--source-root", required=True)
        node_parser.add_argument("--manifest", required=True)
        node_parser.add_argument("--node-id", required=True)
        node_parser.add_argument("--run-id", required=True)
        node_parser.add_argument("--approved-plan-digest")
        node_parser.add_argument("--canary-only", action="store_true")
        node_parser.add_argument(
            "--minimum-workers", type=int, default=DEFAULT_MINIMUM_WORKERS
        )
        node_parser.add_argument("--apply", action="store_true")

    proof_parser = subparsers.add_parser("prove")
    proof_parser.add_argument("--manifest", required=True)
    proof_parser.add_argument("--node-id", required=True)
    proof_parser.add_argument("--campaign-id", required=True)
    proof_parser.add_argument("--duration-seconds", type=int, default=65)

    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = compatibility_plan(
                source_root=Path(args.source_root),
                manifest_path=Path(args.manifest),
                minimum_workers=args.minimum_workers,
                canary_only=args.canary_only,
            )
        elif args.command == "prove":
            control_url = resolve_home_control_plane_url(manifest_path=args.manifest)
            result = submit_long_probe(
                client=ControlPlaneClient(control_url),
                node_id=args.node_id,
                campaign_id=args.campaign_id,
                duration_seconds=args.duration_seconds,
            )
        else:
            bootstrap = NodeBootstrap(
                source_root=Path(args.source_root),
                manifest_path=Path(args.manifest),
                node_id=args.node_id,
                run_id=args.run_id,
                approved_plan_digest=args.approved_plan_digest,
                canary_only=args.canary_only,
                minimum_workers=args.minimum_workers,
            )
            if args.command == "rollback":
                result = bootstrap.rollback() if args.apply else {
                    **bootstrap.plan(),
                    "requested_action": "rollback",
                }
            else:
                result = bootstrap.apply() if args.apply else bootstrap.plan()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("status") not in {"failed", "contract_not_supported"} else 1
    except BootstrapError as exc:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "failed",
                    "error": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
