#!/usr/bin/env python3
"""Root phase for Home Codex provider credential provisioning.

Install this file as a root-owned, non-writable executable before use.  The
owner provisioner passes a private staged verifier record; no raw token enters
this process.  Success always leaves the actor drained.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "kolibri.external-provider-credential.v1"
CONTROL_URL = "http://127.0.0.1:9101"
FACTORY_CONTROL_SERVICE = "kolibri-factory-control.service"
ROOT_RECORD = Path("/etc/kolibri/external-provider-actor.sha256")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class RootPhaseError(RuntimeError):
    def __init__(self, code: str, *, owner_rollback_safe: bool = False):
        super().__init__(code)
        self.code = code
        self.owner_rollback_safe = owner_rollback_safe


def json_line(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_identifier(value: str, field: str) -> str:
    normalized = str(value or "").strip()
    if not SAFE_ID.fullmatch(normalized):
        raise RootPhaseError(f"invalid_{field}")
    return normalized


def read_record(path: Path, *, owner_uid: int, root_owned: bool) -> dict[str, Any]:
    try:
        info = path.lstat()
        expected_uid = 0 if root_owned else owner_uid
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != expected_uid
            or not 64 <= info.st_size <= 2048
        ):
            raise RootPhaseError("verifier_record_unsafe")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except RootPhaseError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RootPhaseError("verifier_record_unsafe") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "credential_id", "node_id", "epoch", "token_sha256"}
        or payload.get("schema_version") != SCHEMA_VERSION
        or type(payload.get("epoch")) is not int
        or int(payload["epoch"]) < 1
        or not SHA256_RE.fullmatch(str(payload.get("token_sha256") or ""))
    ):
        raise RootPhaseError("verifier_record_invalid")
    validate_identifier(str(payload.get("credential_id") or ""), "credential_id")
    validate_identifier(str(payload.get("node_id") or ""), "node_id")
    return payload


def request_json(method: str, path: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = None if body is None else json_line(body).encode("utf-8")
    request = urllib.request.Request(
        f"{CONTROL_URL}{path}",
        data=payload,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 - fixed loopback URL
            parsed = json.loads(response.read(1024 * 1024).decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, urllib.error.URLError) as exc:
        raise RootPhaseError("home_control_plane_unavailable") from exc
    if not isinstance(parsed, dict):
        raise RootPhaseError("home_control_plane_invalid_response")
    return parsed


def restart_factory_control() -> None:
    try:
        completed = subprocess.run(
            ["/usr/bin/systemctl", "restart", FACTORY_CONTROL_SERVICE],
            check=False,
            capture_output=True,
            timeout=45,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RootPhaseError("home_control_plane_restart_failed") from exc
    if completed.returncode != 0:
        raise RootPhaseError("home_control_plane_restart_failed")


def atomic_root_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = path.parent.lstat()
    if stat.S_ISLNK(parent.st_mode) or not stat.S_ISDIR(parent.st_mode):
        raise RootPhaseError("root_verifier_directory_unsafe")
    os.chown(path.parent, 0, 0)
    os.chmod(path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(temporary, 0, 0)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def require_quiescent_control_plane(node_id: str) -> None:
    request_json("POST", f"/v1/nodes/{node_id}/drain", {"drain": True})
    diagnostics = request_json("GET", "/v1/tasks/queue/diagnostics")
    required = {
        "redis": "PONG",
        "lease_index_total": 0,
        "expired_leases": 0,
        "stuck_heartbeat_tasks": 0,
    }
    if any(diagnostics.get(key) != value for key, value in required.items()):
        raise RootPhaseError("home_control_plane_not_quiescent")


def wait_for_binding(node_id: str, credential_id: str, epoch: int) -> None:
    for _attempt in range(20):
        try:
            request_json("GET", "/v1/health")
            actors = request_json("GET", "/v1/runtime/provider-actors?runner=codex&limit=1")
            binding = actors.get("auth_binding")
            if (
                actors.get("auth_configured") is True
                and isinstance(binding, dict)
                and binding.get("bound_node_id") == node_id
                and binding.get("credential_id") == credential_id
                and binding.get("epoch") == epoch
            ):
                return
        except RootPhaseError:
            pass
        time.sleep(1)
    raise RootPhaseError("home_control_plane_binding_unverified")


def apply_root_phase(
    *,
    stage: Path,
    target: Path,
    node_id: str,
    owner_uid: int,
    rotate: bool,
) -> dict[str, Any]:
    try:
        staged = read_record(stage, owner_uid=owner_uid, root_owned=False)
        if staged["node_id"] != node_id:
            raise RootPhaseError("verifier_record_node_mismatch")

        target_exists = target.exists() or target.is_symlink()
        existing = read_record(target, owner_uid=owner_uid, root_owned=True) if target_exists else None
        if rotate:
            if existing is None:
                raise RootPhaseError("verifier_rotation_source_missing")
            if existing["node_id"] != node_id:
                raise RootPhaseError("verifier_rotation_node_mismatch")
            if staged["epoch"] != int(existing["epoch"]) + 1:
                raise RootPhaseError("verifier_epoch_not_increasing")
        elif existing is not None:
            raise RootPhaseError("verifier_exists_rotate_required")

        require_quiescent_control_plane(node_id)
    except RootPhaseError as exc:
        raise RootPhaseError(exc.code, owner_rollback_safe=True) from exc
    previous = target.read_bytes() if existing is not None else None
    installed = False
    try:
        atomic_root_write(target, (json_line(staged) + "\n").encode("utf-8"))
        installed = True
        restart_factory_control()
        wait_for_binding(node_id, str(staged["credential_id"]), int(staged["epoch"]))
    except Exception as original:
        if installed:
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                atomic_root_write(target, previous)
            try:
                restart_factory_control()
            except RootPhaseError as rollback_error:
                raise RootPhaseError(
                    "root_rollback_unverified_actor_drained",
                    owner_rollback_safe=False,
                ) from rollback_error
        code = original.code if isinstance(original, RootPhaseError) else "root_phase_failed"
        raise RootPhaseError(code, owner_rollback_safe=True) from original

    return {
        "status": "binding_verified_actor_drained",
        "node_id": node_id,
        "credential_id": staged["credential_id"],
        "epoch": staged["epoch"],
        "secrets_returned": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--owner-uid", type=int, required=True)
    parser.add_argument("--rotate", action="store_true")
    args = parser.parse_args(argv)

    if os.geteuid() != 0:
        raise RootPhaseError("root_phase_requires_root")
    if args.owner_uid <= 0:
        raise RootPhaseError("owner_uid_invalid")
    if args.target != ROOT_RECORD:
        raise RootPhaseError("root_verifier_destination_fixed")
    node_id = validate_identifier(args.node_id, "node_id")
    result = apply_root_phase(
        stage=args.stage,
        target=args.target,
        node_id=node_id,
        owner_uid=args.owner_uid,
        rotate=args.rotate,
    )
    print(json_line(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RootPhaseError as exc:
        print(json_line({
            "status": "failed",
            "error": exc.code,
            "owner_rollback_safe": exc.owner_rollback_safe,
            "secrets_returned": False,
        }))
        raise SystemExit(1)
