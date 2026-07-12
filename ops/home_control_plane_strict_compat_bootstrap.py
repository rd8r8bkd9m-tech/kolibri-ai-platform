#!/usr/bin/env python3
"""One-time, digest-bound compatibility repair for the Home Control Plane.

The bootstrap changes exactly one legacy-split runtime file and restarts only
``kolibri-factory-control.service``.  Planning is the default.  Apply requires
the exact plan digest produced against the current Home state.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import socket
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

try:
    from ops.control_plane_endpoint import assert_local_home_control_plane
    from ops.fleet_membership import MeshMembershipSource
except ImportError:  # staged beside the canonical runtime modules
    from control_plane_endpoint import assert_local_home_control_plane  # type: ignore[no-redef]
    from fleet_membership import MeshMembershipSource  # type: ignore[no-redef]


SCHEMA_VERSION = "kolibri.home-control-plane-strict-compat-bootstrap.v1"
SERVICE = "kolibri-factory-control.service"
LIVE_URL = "http://127.0.0.1:9101"
TARGET = "/usr/local/bin/kolibri-factory-control"
TARGET_SOURCE = "ops/factory_control.py"
BACKUP_BASE = "/var/backups/kolibri/control-plane-strict-compat"
LOCK_PATH = "/run/lock/kolibri-home-control-plane-strict-compat.lock"
SAFE_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}")
SAFE_COMMIT = re.compile(r"[0-9a-f]{40,64}")
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_HTTP_BYTES = 8 * 1024 * 1024
ANCHORS = {
    "ops/control_plane_endpoint.py": "/usr/local/lib/kolibri/control_plane_endpoint.py",
    "ops/fleet_membership.py": "/usr/local/lib/kolibri/fleet_membership.py",
    "ops/home_control_plane_launcher.py": "/usr/local/lib/kolibri/home_control_plane_launcher.py",
    "ops/release_authority.py": "/usr/local/lib/kolibri/release_authority.py",
    "ops/telegram_superfactory.py": "/usr/local/lib/kolibri/telegram_superfactory.py",
}
CONTRACT_SOURCES = (
    "contracts/kolibri-os-v1/domain.schema.json",
    "contracts/kolibri-os-v1/openapi.json",
    "ops/agent_host.py",
)


class BootstrapError(RuntimeError):
    """Sanitized bootstrap failure suitable for owner evidence."""

    def __init__(self, code: str, *, rollback: str | None = None):
        super().__init__(code)
        self.code = code
        self.rollback = rollback


class CommandRunner(Protocol):
    def run(
        self, argv: Sequence[str], *, timeout: int = 30
    ) -> subprocess.CompletedProcess[str]: ...


class SubprocessRunner:
    def run(
        self, argv: Sequence[str], *, timeout: int = 30
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [str(item) for item in argv],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise BootstrapError("strict_compat_command_unavailable") from exc


@dataclass(frozen=True)
class ServiceState:
    load_state: str
    active_state: str
    sub_state: str
    restarts: int


def _rooted(root: Path, logical: str) -> Path:
    path = Path(logical)
    if not path.is_absolute():
        raise BootstrapError("strict_compat_path_invalid")
    return root / path.relative_to("/")


def _read_regular(path: Path, code: str) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_size <= 0
                or before.st_size > MAX_FILE_BYTES
                or stat.S_IMODE(before.st_mode) & 0o022
            ):
                raise BootstrapError(code)
            payload = handle.read(MAX_FILE_BYTES + 1)
            after = os.fstat(handle.fileno())
        if (
            len(payload) > MAX_FILE_BYTES
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise BootstrapError(code)
        return payload
    except BootstrapError:
        raise
    except OSError as exc:
        raise BootstrapError(code) from exc


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def plan_digest(binding: Mapping[str, Any]) -> str:
    return _sha256(_canonical_bytes(binding))


def _http_json(base_url: str, path: str, timeout: float = 3.0) -> dict[str, Any]:
    request = urllib.request.Request(f"{base_url.rstrip('/')}{path}", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise BootstrapError("strict_compat_contract_unavailable")
            raw = response.read(MAX_HTTP_BYTES + 1)
    except BootstrapError:
        raise
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise BootstrapError("strict_compat_contract_unavailable") from exc
    if not raw or len(raw) > MAX_HTTP_BYTES:
        raise BootstrapError("strict_compat_contract_invalid")
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BootstrapError("strict_compat_contract_invalid") from exc
    if not isinstance(value, dict):
        raise BootstrapError("strict_compat_contract_invalid")
    return value


def _atomic_write(path: Path, payload: bytes, *, mode: int, uid: int, gid: int) -> None:
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
        raise BootstrapError("strict_compat_install_failed") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class StrictCompatBootstrap:
    def __init__(
        self,
        *,
        source_root: Path,
        manifest_path: Path,
        source_commit: str,
        run_id: str,
        root: Path = Path("/"),
        live_url: str = LIVE_URL,
        runner: CommandRunner | None = None,
        local_addresses: Sequence[str] | None = None,
    ) -> None:
        self.source_root = source_root.resolve()
        self.manifest_path = manifest_path.resolve()
        self.source_commit = source_commit
        self.run_id = run_id
        self.root = root.resolve()
        self.live_url = live_url
        self.runner = runner or SubprocessRunner()
        self.local_addresses = local_addresses
        self.source_payload: bytes | None = None
        self.target_payload: bytes | None = None

    def path(self, logical: str) -> Path:
        return _rooted(self.root, logical)

    def _validate_sources_and_anchors(self) -> dict[str, str]:
        if not SAFE_COMMIT.fullmatch(self.source_commit):
            raise BootstrapError("strict_compat_source_commit_invalid")
        if self.root == Path("/"):
            resolved = self.runner.run(
                ["/usr/bin/git", "-C", str(self.source_root), "rev-parse", "HEAD"],
                timeout=10,
            )
            if (
                resolved.returncode != 0
                or resolved.stdout.strip().lower() != self.source_commit
            ):
                raise BootstrapError("strict_compat_source_commit_mismatch")
            scoped_paths = [
                TARGET_SOURCE,
                *ANCHORS.keys(),
                *CONTRACT_SOURCES,
            ]
            clean = self.runner.run(
                [
                    "/usr/bin/git",
                    "-C",
                    str(self.source_root),
                    "diff",
                    "--quiet",
                    "HEAD",
                    "--",
                    *scoped_paths,
                ],
                timeout=10,
            )
            if clean.returncode != 0:
                raise BootstrapError("strict_compat_source_scope_dirty")
        source = self.source_root / TARGET_SOURCE
        payload = _read_regular(source, "strict_compat_source_invalid")
        try:
            compile(payload, TARGET_SOURCE, "exec")
        except (SyntaxError, ValueError) as exc:
            raise BootstrapError("strict_compat_source_invalid") from exc
        self.source_payload = payload

        anchor_digests: dict[str, str] = {}
        for relative, logical in ANCHORS.items():
            expected = _read_regular(
                self.source_root / relative, "strict_compat_anchor_source_invalid"
            )
            actual = _read_regular(
                self.path(logical), "strict_compat_anchor_runtime_invalid"
            )
            if expected != actual:
                raise BootstrapError("strict_compat_anchor_runtime_mismatch")
            if self.root == Path("/") and self.path(logical).lstat().st_uid != 0:
                raise BootstrapError("strict_compat_anchor_runtime_invalid")
            anchor_digests[logical] = _sha256(actual)

        target = self.path(TARGET)
        self.target_payload = _read_regular(target, "strict_compat_target_invalid")
        if self.root == Path("/"):
            target_stat = target.lstat()
            if target_stat.st_uid != 0 or target_stat.st_gid != 0:
                raise BootstrapError("strict_compat_target_invalid")
        return dict(sorted(anchor_digests.items()))

    def _contract_freeze(self) -> dict[str, Any]:
        payloads = {
            relative: _read_regular(
                self.source_root / relative, "strict_compat_contract_source_invalid"
            )
            for relative in CONTRACT_SOURCES
        }
        try:
            domain = json.loads(
                payloads["contracts/kolibri-os-v1/domain.schema.json"]
            )
            openapi = json.loads(payloads["contracts/kolibri-os-v1/openapi.json"])
            compile(payloads["ops/agent_host.py"], "ops/agent_host.py", "exec")
        except (SyntaxError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise BootstrapError("strict_compat_contract_source_invalid") from exc
        try:
            plan_properties = domain["$defs"]["PlanNode"]["properties"]
            retry_required = domain["$defs"]["RetryPolicy"]["required"]
            paths = openapi["paths"]
        except (KeyError, TypeError) as exc:
            raise BootstrapError("strict_compat_contract_freeze_incomplete") from exc
        if not {
            "attempt_id",
            "lease_owner",
            "lease_until",
            "verifier_gates",
        }.issubset(plan_properties) or "max_attempts" not in retry_required:
            raise BootstrapError("strict_compat_contract_freeze_incomplete")
        if not {"/v1/tasks", "/v1/tasks/{task_id}/events"}.issubset(paths):
            raise BootstrapError("strict_compat_contract_freeze_incomplete")
        agent_host = payloads["ops/agent_host.py"]
        control = self.source_payload or b""
        agent_markers = (
            b'"attempt_id": task.get("attempt_id")',
            b'"fencing_token": task.get("fencing_token")',
            b'"result_reference": str(result_path)',
            b'/complete',
            b'/heartbeat',
        )
        control_markers = (
            b"COMPLETION_EVIDENCE_SCHEMA",
            b"allocate_next_fencing_token",
            b'"independent": True',
            b"completion_verifier",
        )
        if any(marker not in agent_host for marker in agent_markers) or any(
            marker not in control for marker in control_markers
        ):
            raise BootstrapError("strict_compat_runner_control_contract_mismatch")
        source_sha256 = {
            relative: _sha256(payload) for relative, payload in sorted(payloads.items())
        }
        return {
            "status": "candidate",
            "source_sha256": source_sha256,
            "digest": plan_digest(source_sha256),
        }

    def _service_state(self) -> ServiceState:
        completed = self.runner.run(
            [
                "/usr/bin/systemctl",
                "show",
                SERVICE,
                "--property=LoadState",
                "--property=ActiveState",
                "--property=SubState",
                "--property=NRestarts",
                "--no-pager",
            ],
            timeout=10,
        )
        if completed.returncode != 0:
            raise BootstrapError("strict_compat_service_unavailable")
        values: dict[str, str] = {}
        for line in completed.stdout.splitlines():
            key, separator, value = line.partition("=")
            if separator:
                values[key] = value
        try:
            state = ServiceState(
                load_state=values["LoadState"],
                active_state=values["ActiveState"],
                sub_state=values["SubState"],
                restarts=int(values["NRestarts"]),
            )
        except (KeyError, ValueError) as exc:
            raise BootstrapError("strict_compat_service_state_invalid") from exc
        if (state.load_state, state.active_state, state.sub_state) != (
            "loaded",
            "active",
            "running",
        ):
            raise BootstrapError("strict_compat_service_not_running")
        return state

    def _launcher_selection(self) -> dict[str, str]:
        launcher = self.path("/usr/local/lib/kolibri/home_control_plane_launcher.py")
        completed = self.runner.run(
            ["/usr/bin/python3", "-B", str(launcher), "--print-selection"],
            timeout=10,
        )
        try:
            payload = json.loads(completed.stdout) if completed.returncode == 0 else {}
        except json.JSONDecodeError as exc:
            raise BootstrapError("strict_compat_launcher_selection_invalid") from exc
        if (
            payload.get("status") != "selected"
            or payload.get("authority") != "home"
            or payload.get("source") != "legacy-split-bootstrap"
            or payload.get("release_id") != "legacy-bootstrap"
        ):
            raise BootstrapError("strict_compat_launcher_not_legacy_split")
        return {
            "authority": "home",
            "source": "legacy-split-bootstrap",
            "release_id": "legacy-bootstrap",
        }

    def _baseline(self) -> dict[str, Any]:
        health = _http_json(self.live_url, "/v1/health")
        data = health.get("data") if isinstance(health.get("data"), dict) else {}
        diagnostics = _http_json(self.live_url, "/v1/tasks/queue/diagnostics")
        if (
            health.get("status") != "completed"
            or health.get("node") != "home"
            or data.get("redis") != "PONG"
            or diagnostics.get("redis") != "PONG"
        ):
            raise BootstrapError("strict_compat_baseline_invalid")
        for key in ("task_total", "queue_total", "lease_index_total"):
            if type(diagnostics.get(key)) is not int or diagnostics[key] < 0:
                raise BootstrapError("strict_compat_redis_projection_invalid")
        if (
            diagnostics["lease_index_total"] != 0
            or diagnostics.get("expired_leases") != 0
            or diagnostics.get("stuck_heartbeat_tasks") != 0
        ):
            raise BootstrapError("strict_compat_active_or_stale_leases")
        state_namespace = str(
            data.get("state_namespace")
            or os.environ.get("FACTORY_NAMESPACE")
            or ""
        ).strip()
        if not state_namespace:
            raise BootstrapError("strict_compat_state_namespace_unavailable")
        return {
            "state_namespace": state_namespace,
            "redis_projection": {
                key: diagnostics[key]
                for key in ("task_total", "queue_total", "lease_index_total")
            },
        }

    def build_plan(self) -> dict[str, Any]:
        anchors = self._validate_sources_and_anchors()
        contract_freeze = self._contract_freeze()
        snapshot = MeshMembershipSource(self.manifest_path).load()
        try:
            assert_local_home_control_plane(
                manifest_path=self.manifest_path,
                local_addresses=self.local_addresses,
            )
        except Exception as exc:
            raise BootstrapError("strict_compat_target_not_home") from exc
        selection = self._launcher_selection()
        service = self._service_state()
        baseline = self._baseline()
        assert self.source_payload is not None and self.target_payload is not None
        changed = self.source_payload != self.target_payload
        binding: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "target_node": "home",
            "service": SERVICE,
            "source_commit": self.source_commit,
            "membership_digest": snapshot.digest,
            "launcher_selection": selection,
            "target": {
                "path": TARGET,
                "before_sha256": _sha256(self.target_payload),
                "after_sha256": _sha256(self.source_payload),
                "changed": changed,
            },
            "anchor_sha256": anchors,
            "state_namespace": baseline["state_namespace"],
            "contract_freeze_digest": contract_freeze["digest"],
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "planned" if changed else "already_current",
            "mode": "dry-run",
            "target_node": "home",
            "source_commit": self.source_commit,
            "membership_digest": snapshot.digest,
            "changed_paths": [TARGET] if changed else [],
            "restart_units": [SERVICE] if changed else [],
            "untouched": [
                "backend",
                "frontend",
                "credentials",
                "mesh",
                "redis_data",
                "other_systemd_units",
            ],
            "service_before": service.__dict__,
            "redis_before": baseline["redis_projection"],
            "state_namespace": baseline["state_namespace"],
            "contract_freeze": contract_freeze,
            "plan_digest": plan_digest(binding),
            "binding": binding,
        }

    def _strict_contracts(
        self,
        base_url: str,
        *,
        expected_release: str,
        expected_read_only: bool,
        expected_membership_digest: str,
    ) -> dict[str, Any]:
        health = _http_json(base_url, "/v1/health")
        data = health.get("data") if isinstance(health.get("data"), dict) else {}
        if (
            health.get("status") != "completed"
            or health.get("node") != "home"
            or health.get("route_used") != "/v1/health"
            or data.get("redis") != "PONG"
            or data.get("active_release_id") != expected_release
            or data.get("canary_read_only") is not expected_read_only
        ):
            raise BootstrapError("strict_compat_health_contract_invalid")
        nodes = _http_json(base_url, "/v1/nodes?scope=active&limit=250")
        membership = nodes.get("membership") if isinstance(nodes.get("membership"), dict) else {}
        if (
            nodes.get("scope") != "active"
            or membership.get("authority") != "replicated_mesh_manifest"
            or membership.get("digest") != expected_membership_digest
        ):
            raise BootstrapError("strict_compat_membership_contract_invalid")
        proof = _http_json(base_url, "/v1/runtime/fleet-proof")
        proof_membership = proof.get("membership") if isinstance(proof.get("membership"), dict) else {}
        if (
            proof.get("schema_version") != "kolibri.fleet-capability-proof.v1"
            or proof.get("source") != "control-plane/home"
            or proof_membership.get("digest") != expected_membership_digest
        ):
            raise BootstrapError("strict_compat_fleet_proof_invalid")
        diagnostics = _http_json(base_url, "/v1/tasks/queue/diagnostics")
        if diagnostics.get("redis") != "PONG":
            raise BootstrapError("strict_compat_redis_projection_invalid")
        return {
            "health": "strict",
            "membership_digest": expected_membership_digest,
            "redis_projection": {
                key: diagnostics.get(key)
                for key in ("task_total", "queue_total", "lease_index_total")
            },
        }

    def _candidate(self, plan: Mapping[str, Any]) -> dict[str, Any]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])
        candidate_url = f"http://127.0.0.1:{port}"
        environment = dict(os.environ)
        environment.update(
            {
                "FACTORY_BIND": "127.0.0.1",
                "FACTORY_PORT": str(port),
                "FACTORY_CANARY_READ_ONLY": "1",
                "FACTORY_NAMESPACE": str(plan["state_namespace"]),
                "KOLIBRI_ACTIVE_RELEASE_ID": "strict-compat-candidate",
                "KOLIBRI_MESH_MEMBERSHIP_MANIFEST": str(self.manifest_path),
                "KOLIBRI_REPO_ROOT": str(self.source_root),
                "KOLIBRI_OPS_DIR": str(self.source_root / "ops"),
                "PYTHONPATH": f"{self.source_root / 'ops'}:{self.source_root}",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
            }
        )
        try:
            process = subprocess.Popen(
                [
                    "/usr/bin/python3",
                    "-B",
                    str(self.source_root / TARGET_SOURCE),
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=self.source_root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise BootstrapError("strict_compat_candidate_unavailable") from exc
        try:
            deadline = time.monotonic() + 20
            last_error: BootstrapError | None = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise BootstrapError("strict_compat_candidate_exited")
                try:
                    return self._strict_contracts(
                        candidate_url,
                        expected_release="strict-compat-candidate",
                        expected_read_only=True,
                        expected_membership_digest=str(plan["membership_digest"]),
                    )
                except BootstrapError as exc:
                    last_error = exc
                    time.sleep(0.2)
            raise BootstrapError("strict_compat_candidate_timeout") from last_error
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)

    def _restart(self) -> None:
        completed = self.runner.run(
            ["/usr/bin/systemctl", "restart", SERVICE], timeout=30
        )
        if completed.returncode != 0:
            raise BootstrapError("strict_compat_restart_failed")

    def _create_backup_directory(self) -> Path:
        base = self.path("/var/backups")
        if not base.exists():
            raise BootstrapError("strict_compat_backup_root_unavailable")
        cursor = base
        for part in ("kolibri", "control-plane-strict-compat"):
            cursor = cursor / part
            if os.path.lexists(cursor):
                value = cursor.lstat()
                if (
                    not stat.S_ISDIR(value.st_mode)
                    or stat.S_ISLNK(value.st_mode)
                    or stat.S_IMODE(value.st_mode) & 0o022
                    or (self.root == Path("/") and value.st_uid != 0)
                ):
                    raise BootstrapError("strict_compat_backup_root_unsafe")
            else:
                cursor.mkdir(mode=0o700)
                if self.root == Path("/"):
                    os.chown(cursor, 0, 0)
        backup = cursor / self.run_id
        try:
            backup.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise BootstrapError("strict_compat_run_id_already_used") from exc
        if self.root == Path("/"):
            os.chown(backup, 0, 0)
        return backup

    def apply(
        self,
        expected_plan_digest: str,
        expected_contract_freeze_digest: str,
    ) -> dict[str, Any]:
        if self.root == Path("/") and os.geteuid() != 0:
            raise BootstrapError("strict_compat_root_required")
        if not SAFE_RUN_ID.fullmatch(self.run_id):
            raise BootstrapError("strict_compat_run_id_invalid")
        lock_path = self.path(LOCK_PATH)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise BootstrapError("strict_compat_locked") from exc
            plan = self.build_plan()
            if expected_plan_digest != plan["plan_digest"]:
                raise BootstrapError("strict_compat_plan_digest_mismatch")
            if expected_contract_freeze_digest != plan["contract_freeze"]["digest"]:
                raise BootstrapError("strict_compat_contract_freeze_digest_mismatch")
            if not plan["changed_paths"]:
                return {**plan, "status": "already_applied", "mode": "apply"}
            candidate = self._candidate(plan)
            if candidate["redis_projection"] != plan["redis_before"]:
                raise BootstrapError("strict_compat_candidate_redis_state_mismatch")
            before_service = self._service_state()
            assert self.source_payload is not None and self.target_payload is not None
            target = self.path(TARGET)
            target_stat = target.lstat()
            backup = self._create_backup_directory()
            _atomic_write(
                backup / "factory_control.before",
                self.target_payload,
                mode=0o600,
                uid=0 if self.root == Path("/") else os.geteuid(),
                gid=0 if self.root == Path("/") else os.getegid(),
            )
            _atomic_write(
                backup / "plan.json",
                _canonical_bytes(plan),
                mode=0o600,
                uid=0 if self.root == Path("/") else os.geteuid(),
                gid=0 if self.root == Path("/") else os.getegid(),
            )
            installed = False
            try:
                _atomic_write(
                    target,
                    self.source_payload,
                    mode=0o755,
                    uid=0 if self.root == Path("/") else os.geteuid(),
                    gid=0 if self.root == Path("/") else os.getegid(),
                )
                installed = True
                self._restart()
                deadline = time.monotonic() + 20
                last_error: BootstrapError | None = None
                while time.monotonic() < deadline:
                    try:
                        post = self._strict_contracts(
                            self.live_url,
                            expected_release="legacy-bootstrap",
                            expected_read_only=False,
                            expected_membership_digest=str(plan["membership_digest"]),
                        )
                        break
                    except BootstrapError as exc:
                        last_error = exc
                        time.sleep(0.5)
                else:
                    raise BootstrapError("strict_compat_post_health_failed") from last_error
                after_service = self._service_state()
                # A deliberate systemctl restart resets NRestarts. Any
                # non-zero value now means the candidate crashed and systemd
                # restarted it at least once.
                if after_service.restarts != 0:
                    raise BootstrapError("strict_compat_restart_counter_changed")
                if post["redis_projection"] != plan["redis_before"]:
                    raise BootstrapError("strict_compat_redis_state_changed")
            except Exception as exc:
                rollback = "not_required"
                if installed:
                    try:
                        _atomic_write(
                            target,
                            self.target_payload,
                            mode=stat.S_IMODE(target_stat.st_mode),
                            uid=target_stat.st_uid,
                            gid=target_stat.st_gid,
                        )
                        self._restart()
                        rollback_deadline = time.monotonic() + 20
                        last_rollback_error: BootstrapError | None = None
                        while time.monotonic() < rollback_deadline:
                            try:
                                restored = self._baseline()
                                break
                            except BootstrapError as rollback_health_error:
                                last_rollback_error = rollback_health_error
                                time.sleep(0.5)
                        else:
                            raise BootstrapError(
                                "strict_compat_rollback_health_failed"
                            ) from last_rollback_error
                        if restored["redis_projection"] != plan["redis_before"]:
                            raise BootstrapError("strict_compat_rollback_state_changed")
                        rollback = "completed"
                    except Exception as rollback_exc:
                        raise BootstrapError(
                            "strict_compat_rollback_failed", rollback="failed"
                        ) from rollback_exc
                if isinstance(exc, BootstrapError):
                    raise BootstrapError(exc.code, rollback=rollback) from exc
                raise BootstrapError("strict_compat_apply_failed", rollback=rollback) from exc
            evidence = {
                "schema_version": SCHEMA_VERSION,
                "status": "applied",
                "mode": "apply",
                "target_node": "home",
                "source_commit": self.source_commit,
                "plan_digest": plan["plan_digest"],
                "changed_paths": [TARGET],
                "restart_units": [SERVICE],
                "candidate": candidate,
                "post": post,
                "service_before": before_service.__dict__,
                "service_after": after_service.__dict__,
                "backup": str(Path(BACKUP_BASE) / self.run_id),
                "rollback": "armed",
            }
            _atomic_write(
                backup / "result.json",
                _canonical_bytes(evidence),
                mode=0o600,
                uid=0 if self.root == Path("/") else os.geteuid(),
                gid=0 if self.root == Path("/") else os.getegid(),
            )
            return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--manifest", default="/var/lib/kolibri-mesh/peers.json")
    parser.add_argument("--run-id", default=f"strict-compat-{int(time.time())}")
    parser.add_argument("--expected-plan-digest")
    parser.add_argument("--expected-contract-freeze-digest")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        bootstrap = StrictCompatBootstrap(
            source_root=Path(args.source_root),
            manifest_path=Path(args.manifest),
            source_commit=args.source_commit,
            run_id=args.run_id,
        )
        if args.apply:
            if not args.expected_plan_digest:
                raise BootstrapError("strict_compat_expected_plan_digest_required")
            if not args.expected_contract_freeze_digest:
                raise BootstrapError(
                    "strict_compat_expected_contract_freeze_digest_required"
                )
            result = bootstrap.apply(
                args.expected_plan_digest,
                args.expected_contract_freeze_digest,
            )
        else:
            result = bootstrap.build_plan()
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        code = exc.code if isinstance(exc, BootstrapError) else "strict_compat_bootstrap_failed"
        payload: dict[str, Any] = {"status": "blocked", "reason": code}
        if isinstance(exc, BootstrapError) and exc.rollback is not None:
            payload["rollback"] = exc.rollback
        print(json.dumps(payload, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
