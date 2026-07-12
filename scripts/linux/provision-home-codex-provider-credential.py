#!/usr/bin/env python3
"""Dry-run-first scoped credential provisioner for the Home Codex actor.

The owner process keeps the raw token in the Home owner's private provider
directory.  A separately installed, root-owned helper receives only a staged
SHA-256 verifier record and performs the Control Plane drain/restart/rollback
sequence.  Neither process prints the token or its verifier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "kolibri.external-provider-credential.v1"
DEFAULT_NODE_ID = "home-codex-provider"
DEFAULT_CREDENTIAL_ID = "home-codex-provider-v1"
DEFAULT_ROOT_HELPER = Path("/usr/local/libexec/kolibri-home-codex-provider-credential-root")
DEFAULT_ROOT_RECORD = Path("/etc/kolibri/external-provider-actor.sha256")
SUDO = Path("/usr/bin/sudo")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
TOKEN_RE = re.compile(r"[A-Za-z0-9._~-]{32,512}\Z")


class CredentialProvisionError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class RootHelperDefinitiveFailure(CredentialProvisionError):
    """The helper proved that the root record stayed/restored unchanged."""


def json_line(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_identifier(value: str, field: str) -> str:
    normalized = str(value or "").strip()
    if not SAFE_ID.fullmatch(normalized):
        raise CredentialProvisionError(f"invalid_{field}")
    return normalized


def credential_destination(home: Path) -> Path:
    return (
        home.expanduser().resolve()
        / ".local/share/kolibri/home-codex-provider/config/external-provider-actor.credential"
    )


def atomic_write(path: Path, payload: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = path.parent.lstat()
    if stat.S_ISLNK(parent.st_mode) or not stat.S_ISDIR(parent.st_mode):
        raise CredentialProvisionError("credential_directory_unsafe")
    os.chmod(path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_private_token(path: Path) -> str:
    try:
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
            or not 32 <= info.st_size <= 513
        ):
            raise CredentialProvisionError("credential_source_unsafe")
        token = path.read_text(encoding="ascii").strip()
    except CredentialProvisionError:
        raise
    except (OSError, UnicodeError) as exc:
        raise CredentialProvisionError("credential_source_unreadable") from exc
    if not TOKEN_RE.fullmatch(token):
        raise CredentialProvisionError("credential_source_invalid")
    return token


def read_owner_record(path: Path) -> dict[str, Any]:
    try:
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
            or not 64 <= info.st_size <= 2048
        ):
            raise CredentialProvisionError("credential_destination_unsafe")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except CredentialProvisionError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CredentialProvisionError("credential_destination_unsafe") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "credential_id", "node_id", "epoch", "token"}
        or payload.get("schema_version") != SCHEMA_VERSION
        or type(payload.get("epoch")) is not int
        or int(payload["epoch"]) < 1
        or not TOKEN_RE.fullmatch(str(payload.get("token") or ""))
    ):
        raise CredentialProvisionError("credential_destination_invalid")
    validate_identifier(str(payload.get("credential_id") or ""), "credential_id")
    validate_identifier(str(payload.get("node_id") or ""), "node_id")
    return payload


def validate_root_helper(path: Path) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
        info = resolved.stat()
    except OSError as exc:
        raise CredentialProvisionError("approved_root_helper_unavailable") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or stat.S_IMODE(info.st_mode) & 0o022
        or not os.access(resolved, os.X_OK)
    ):
        raise CredentialProvisionError("approved_root_helper_unsafe")
    return resolved


def run_root_helper(
    helper: Path,
    *,
    stage: Path,
    target: Path,
    node_id: str,
    owner_uid: int,
    rotate: bool,
    migrate_from: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    command = [
        str(SUDO), "-n", "--",
        str(helper),
        "--stage", str(stage),
        "--target", str(target),
        "--node-id", node_id,
        "--owner-uid", str(owner_uid),
    ]
    if rotate:
        command.append("--rotate")
    if migrate_from is not None:
        command.extend([
            "--migrate-from-node-id", str(migrate_from["node_id"]),
            "--migrate-from-credential-id", str(migrate_from["credential_id"]),
            "--migrate-from-epoch", str(migrate_from["epoch"]),
        ])
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
            env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CredentialProvisionError("root_helper_state_uncertain_actor_drained") from exc
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CredentialProvisionError("root_helper_state_uncertain_actor_drained") from exc
    if completed.returncode != 0:
        if isinstance(payload, dict) and payload.get("owner_rollback_safe") is True:
            root_error = str(payload.get("error") or "").strip()
            if not SAFE_ID.fullmatch(root_error):
                root_error = "root_helper_failed_root_state_unchanged"
            raise RootHelperDefinitiveFailure(root_error)
        raise CredentialProvisionError("root_helper_state_uncertain_actor_drained")
    expected = {
        "status": "binding_verified_actor_drained",
        "node_id": node_id,
        "secrets_returned": False,
    }
    if not isinstance(payload, dict) or any(payload.get(key) != value for key, value in expected.items()):
        raise CredentialProvisionError("root_helper_state_uncertain_actor_drained")
    if type(payload.get("epoch")) is not int or int(payload["epoch"]) < 1:
        raise CredentialProvisionError("root_helper_state_uncertain_actor_drained")
    validate_identifier(str(payload.get("credential_id") or ""), "credential_id")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-id", default=DEFAULT_NODE_ID)
    parser.add_argument("--credential-id", default=DEFAULT_CREDENTIAL_ID)
    parser.add_argument("--epoch", type=int, default=1)
    parser.add_argument("--credential-source", type=Path)
    parser.add_argument("--root-helper", type=Path, default=DEFAULT_ROOT_HELPER)
    parser.add_argument("--root-record", type=Path, default=DEFAULT_ROOT_RECORD)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rotate", action="store_true")
    parser.add_argument("--migrate-from-node-id")
    parser.add_argument("--migrate-from-credential-id")
    parser.add_argument("--migrate-from-epoch", type=int)
    args = parser.parse_args(argv)

    if os.geteuid() == 0:
        raise CredentialProvisionError("provisioner_must_run_as_home_owner")
    node_id = validate_identifier(args.node_id, "node_id")
    credential_id = validate_identifier(args.credential_id, "credential_id")
    if args.epoch < 1:
        raise CredentialProvisionError("credential_epoch_invalid")
    if args.root_record != DEFAULT_ROOT_RECORD:
        raise CredentialProvisionError("root_verifier_destination_fixed")

    migration_values = (
        args.migrate_from_node_id,
        args.migrate_from_credential_id,
        args.migrate_from_epoch,
    )
    migration_requested = any(value is not None for value in migration_values)
    if migration_requested and not all(value is not None for value in migration_values):
        raise CredentialProvisionError("credential_migration_binding_incomplete")
    if migration_requested and args.rotate:
        raise CredentialProvisionError("credential_migration_and_rotation_conflict")
    migrate_from: dict[str, Any] | None = None
    if migration_requested:
        migrate_from = {
            "node_id": validate_identifier(args.migrate_from_node_id, "migration_node_id"),
            "credential_id": validate_identifier(
                args.migrate_from_credential_id, "migration_credential_id",
            ),
            "epoch": int(args.migrate_from_epoch),
        }
        if migrate_from["epoch"] < 1:
            raise CredentialProvisionError("credential_migration_epoch_invalid")
        if args.epoch != migrate_from["epoch"] + 1:
            raise CredentialProvisionError("credential_migration_epoch_not_increasing")
        if migrate_from["node_id"] == node_id:
            raise CredentialProvisionError("credential_migration_node_unchanged")

    owner_path = credential_destination(Path.home())
    destination_exists = owner_path.exists() or owner_path.is_symlink()
    existing = read_owner_record(owner_path) if destination_exists else None
    if migrate_from is not None and existing is not None:
        raise CredentialProvisionError("credential_migration_owner_destination_exists")
    if args.apply and destination_exists and not args.rotate:
        raise CredentialProvisionError("credential_exists_rotate_required")
    if args.rotate and existing is None:
        raise CredentialProvisionError("credential_rotation_source_missing")
    if existing is not None:
        if existing["node_id"] != node_id:
            raise CredentialProvisionError("credential_rotation_node_mismatch")
        if args.rotate and args.epoch != int(existing["epoch"]) + 1:
            raise CredentialProvisionError("credential_epoch_not_increasing")
    if args.credential_source is not None:
        read_private_token(args.credential_source.expanduser())

    plan: dict[str, Any] = {
        "schema_version": "kolibri.home-provider-credential-provision.v1",
        "status": "validated",
        "apply": args.apply,
        "rotate": args.rotate,
        "migration": migrate_from,
        "node_id": node_id,
        "credential_id": credential_id,
        "epoch": args.epoch,
        "owner_destination": str(owner_path),
        "root_verifier_destination": str(args.root_record),
        "root_phase": "approved_root_helper",
        "actor_final_state": "drained",
        "secrets_returned": False,
    }
    if not args.apply:
        print(json_line(plan))
        return 0

    helper = validate_root_helper(args.root_helper)
    token = (
        read_private_token(args.credential_source.expanduser())
        if args.credential_source is not None
        else secrets.token_urlsafe(48)
    )
    if not TOKEN_RE.fullmatch(token):
        raise CredentialProvisionError("generated_credential_invalid")

    owner_record = {
        "schema_version": SCHEMA_VERSION,
        "credential_id": credential_id,
        "node_id": node_id,
        "epoch": args.epoch,
        "token": token,
    }
    root_record = {
        "schema_version": SCHEMA_VERSION,
        "credential_id": credential_id,
        "node_id": node_id,
        "epoch": args.epoch,
        "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
    }
    previous = owner_path.read_bytes() if destination_exists else None
    stage_directory = owner_path.parent / ".root-stage"
    stage_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(stage_directory, 0o700)
    descriptor, stage_name = tempfile.mkstemp(prefix="credential.", dir=stage_directory)
    stage = Path(stage_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write((json_line(root_record) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(stage, 0o600)
        atomic_write(owner_path, (json_line(owner_record) + "\n").encode("utf-8"), 0o600)
        try:
            result = run_root_helper(
                helper,
                stage=stage,
                target=args.root_record,
                node_id=node_id,
                owner_uid=os.getuid(),
                rotate=args.rotate,
                migrate_from=migrate_from,
            )
        except RootHelperDefinitiveFailure:
            if previous is None:
                owner_path.unlink(missing_ok=True)
            else:
                atomic_write(owner_path, previous, 0o600)
            raise
    finally:
        stage.unlink(missing_ok=True)
        try:
            stage_directory.rmdir()
        except OSError:
            pass

    if result.get("credential_id") != credential_id or result.get("epoch") != args.epoch:
        # The helper already committed an exact binding.  Keep the actor drained
        # and fail closed rather than guessing whether a rollback is safe.
        raise CredentialProvisionError("root_helper_binding_mismatch_actor_drained")
    plan.update({
        "status": (
            "credential_migrated_actor_drained"
            if migrate_from is not None
            else "credential_rotated_actor_drained"
            if args.rotate
            else "credential_installed_actor_drained"
        ),
        "binding_verified": True,
        "secrets_returned": False,
        "next_action": "install/start provider runtime, verify readiness and canary, then separately approve undrain",
    })
    print(json_line(plan))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CredentialProvisionError as exc:
        print(json_line({"status": "failed", "error": exc.code, "secrets_returned": False}))
        raise SystemExit(1)
