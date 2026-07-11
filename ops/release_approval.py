#!/usr/bin/env python3
"""Build, sign, and submit a release-scoped owner approval safely.

``plan`` is read-only and does not access an owner private key.  ``sign`` is
an explicit local write and passes the key path only to ``ssh-keygen``.  The
separate ``submit`` command verifies the signed approval locally and sends it
only to the canonical Home Control Plane.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from ops.release_authority import (
        OWNER_APPROVAL_NAMESPACE,
        ReleaseAuthorityError,
        canonical_owner_approval_bytes,
        canonical_owner_approval_payload,
        canonical_rollout_plan,
    )
    from ops.release_controller import (
        ControlPlaneClient,
        ReleaseError,
        ReleaseManifest,
        VerifiedRelease,
        load_release_manifest,
        verify_ssh_signature,
    )
except ImportError:  # installed standalone beside the release modules
    from release_authority import (  # type: ignore[no-redef]
        OWNER_APPROVAL_NAMESPACE,
        ReleaseAuthorityError,
        canonical_owner_approval_bytes,
        canonical_owner_approval_payload,
        canonical_rollout_plan,
    )
    from release_controller import (  # type: ignore[no-redef]
        ControlPlaneClient,
        ReleaseError,
        ReleaseManifest,
        VerifiedRelease,
        load_release_manifest,
        verify_ssh_signature,
    )


CLI_SCHEMA = "kolibri.release-approval-cli.v1"
MAX_JSON_BYTES = 128 * 1024
MAX_SIGNATURE_BYTES = 32 * 1024
DEFAULT_MAX_TTL_SECONDS = 24 * 60 * 60


class ReleaseApprovalError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ReleaseApprovalError("release_approval_json_invalid") from exc


def _read_regular_bytes(path: Path, *, max_bytes: int, code: str) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink < 1
                or before.st_size <= 0
                or before.st_size > max_bytes
            ):
                raise ReleaseApprovalError(code)
            payload = handle.read(max_bytes + 1)
            after = os.fstat(handle.fileno())
    except ReleaseApprovalError:
        raise
    except OSError as exc:
        raise ReleaseApprovalError(code) from exc
    if (
        len(payload) > max_bytes
        or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ReleaseApprovalError(code)
    return payload


def _load_json_object(path: Path, *, code: str) -> dict[str, Any]:
    raw = _read_regular_bytes(path, max_bytes=MAX_JSON_BYTES, code=code)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseApprovalError(code) from exc
    if not isinstance(value, dict):
        raise ReleaseApprovalError(code)
    return value


def load_bound_rollout_plan(path: Path, release: ReleaseManifest) -> list[dict[str, Any]]:
    value = _load_json_object(path, code="release_approval_rollout_plan_invalid")
    if (
        value.get("schema_version") != release.schema_version
        or value.get("release_id") != release.release_id
        or value.get("manifest_digest") != release.digest
        or value.get("transport") != "control-plane-api-only"
    ):
        raise ReleaseApprovalError("release_approval_rollout_plan_binding_mismatch")
    try:
        return canonical_rollout_plan(value.get("waves"))
    except ReleaseAuthorityError as exc:
        raise ReleaseApprovalError(str(exc)) from exc


def load_verified_release(
    manifest_path: Path,
    signature_path: Path,
    allowed_signers_path: Path,
    signer_identity: str,
) -> VerifiedRelease:
    try:
        manifest = load_release_manifest(manifest_path)
        return verify_ssh_signature(
            manifest,
            signature_path,
            allowed_signers_path,
            signer_identity,
        )
    except ReleaseError as exc:
        raise ReleaseApprovalError("release_approval_release_signature_invalid") from exc


def build_approval_payload(
    *,
    verified: VerifiedRelease,
    rollback: VerifiedRelease,
    rollout_plan: list[dict[str, Any]],
    approval_id: str,
    expires_at: str,
    nonce: str,
    owner_signer_identity: str,
    max_ttl_seconds: int = DEFAULT_MAX_TTL_SECONDS,
) -> dict[str, Any]:
    try:
        return canonical_owner_approval_payload(
            {
                "approval_id": approval_id,
                "release_id": verified.manifest.release_id,
                "manifest_digest": verified.manifest.digest,
                "release_signature_namespace": verified.namespace,
                "release_signer_identity": verified.signer_identity,
                "decision": "approved",
                "allow_rollback": True,
                "rollback": {
                    "release_id": rollback.manifest.release_id,
                    "manifest_digest": rollback.manifest.digest,
                    "signature_namespace": rollback.namespace,
                    "signer_identity": rollback.signer_identity,
                },
                "rollout_plan": rollout_plan,
                "expires_at": expires_at,
                "nonce": nonce,
                "signer_identity": owner_signer_identity,
            },
            max_ttl_seconds=max_ttl_seconds,
        )
    except ReleaseAuthorityError as exc:
        raise ReleaseApprovalError(str(exc)) from exc


def _safe_signing_environment() -> dict[str, str]:
    result = {
        key: value
        for key, value in os.environ.items()
        if key in {"HOME", "LANG", "LC_ALL", "PATH", "TMPDIR"}
    }
    result["SSH_ASKPASS_REQUIRE"] = "never"
    result.pop("DISPLAY", None)
    return result


def _validate_executable(path: Path) -> Path:
    try:
        value = path.lstat()
    except OSError as exc:
        raise ReleaseApprovalError("release_approval_ssh_keygen_unavailable") from exc
    if not stat.S_ISREG(value.st_mode) or not value.st_mode & 0o111:
        raise ReleaseApprovalError("release_approval_ssh_keygen_unavailable")
    return path


def _validate_private_key_path(path: Path) -> tuple[Path, os.stat_result]:
    try:
        value = path.lstat()
        parent = path.parent.lstat()
    except OSError as exc:
        raise ReleaseApprovalError("release_approval_signing_key_unavailable") from exc
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_nlink < 1
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) & 0o077
        or not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid not in {0, os.geteuid()}
        or stat.S_IMODE(parent.st_mode) & 0o022
    ):
        raise ReleaseApprovalError("release_approval_signing_key_permissions_invalid")
    return path, value


def _run_ssh_keygen(command: list[str], *, input_bytes: bytes | None = None) -> None:
    try:
        completed = subprocess.run(
            command,
            input=input_bytes,
            stdin=subprocess.DEVNULL if input_bytes is None else None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_safe_signing_environment(),
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseApprovalError("release_approval_signature_operation_failed") from exc
    if completed.returncode != 0:
        raise ReleaseApprovalError("release_approval_signature_operation_failed")


def sign_approval_payload(
    payload: dict[str, Any],
    *,
    signing_key: Path,
    ssh_keygen: Path,
) -> str:
    ssh_keygen = _validate_executable(ssh_keygen)
    signing_key, key_before = _validate_private_key_path(signing_key)
    canonical = canonical_owner_approval_bytes(payload)
    generated: Path | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="kolibri-owner-approval-sign-") as temporary:
            approval_path = Path(temporary) / "approval.json"
            descriptor = os.open(approval_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(canonical)
                handle.flush()
                os.fsync(handle.fileno())
            _run_ssh_keygen([
                str(ssh_keygen),
                "-Y",
                "sign",
                "-f",
                str(signing_key),
                "-n",
                OWNER_APPROVAL_NAMESPACE,
                str(approval_path),
            ])
            generated = Path(f"{approval_path}.sig")
            signature = _read_regular_bytes(
                generated,
                max_bytes=MAX_SIGNATURE_BYTES,
                code="release_approval_signature_invalid",
            )
    finally:
        if generated is not None:
            try:
                generated.unlink(missing_ok=True)
            except OSError:
                pass
    try:
        key_after = signing_key.lstat()
    except OSError as exc:
        raise ReleaseApprovalError("release_approval_signing_key_unstable") from exc
    if (
        key_before.st_dev != key_after.st_dev
        or key_before.st_ino != key_after.st_ino
        or key_before.st_size != key_after.st_size
        or key_before.st_mtime_ns != key_after.st_mtime_ns
        or stat.S_IMODE(key_before.st_mode) != stat.S_IMODE(key_after.st_mode)
    ):
        raise ReleaseApprovalError("release_approval_signing_key_unstable")
    try:
        text = signature.decode("ascii")
    except UnicodeError as exc:
        raise ReleaseApprovalError("release_approval_signature_invalid") from exc
    if not text.startswith("-----BEGIN SSH SIGNATURE-----"):
        raise ReleaseApprovalError("release_approval_signature_invalid")
    return text


def verify_signed_approval(
    body: dict[str, Any],
    *,
    allowed_signers: Path,
    ssh_keygen: Path,
) -> dict[str, Any]:
    expected_keys = {
        "schema_version",
        "approval_id",
        "release_id",
        "manifest_digest",
        "release_signature_namespace",
        "release_signer_identity",
        "decision",
        "allow_rollback",
        "rollback",
        "rollout_plan",
        "expires_at",
        "nonce",
        "signer_identity",
        "signature",
    }
    if set(body) != expected_keys:
        raise ReleaseApprovalError("release_approval_file_invalid")
    signature = body.get("signature")
    if not isinstance(signature, str) or not signature.startswith("-----BEGIN SSH SIGNATURE-----"):
        raise ReleaseApprovalError("release_approval_signature_invalid")
    try:
        payload = canonical_owner_approval_payload(
            {key: value for key, value in body.items() if key != "signature"},
            max_ttl_seconds=DEFAULT_MAX_TTL_SECONDS,
        )
    except ReleaseAuthorityError as exc:
        raise ReleaseApprovalError(str(exc)) from exc
    ssh_keygen = _validate_executable(ssh_keygen)
    _read_regular_bytes(
        allowed_signers,
        max_bytes=MAX_JSON_BYTES,
        code="release_approval_allowed_signers_invalid",
    )
    with tempfile.TemporaryDirectory(prefix="kolibri-owner-approval-verify-") as temporary:
        signature_path = Path(temporary) / "approval.sig"
        descriptor = os.open(signature_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(signature.encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
        _run_ssh_keygen(
            [
                str(ssh_keygen),
                "-Y",
                "verify",
                "-f",
                str(allowed_signers),
                "-I",
                payload["signer_identity"],
                "-n",
                OWNER_APPROVAL_NAMESPACE,
                "-s",
                str(signature_path),
            ],
            input_bytes=canonical_owner_approval_bytes(payload),
        )
    return payload


def _publish_private_json(output: Path, value: dict[str, Any]) -> None:
    try:
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        parent = output.parent.resolve(strict=True)
        parent_value = parent.lstat()
    except OSError as exc:
        raise ReleaseApprovalError("release_approval_output_invalid") from exc
    if (
        not stat.S_ISDIR(parent_value.st_mode)
        or parent_value.st_uid not in {0, os.geteuid()}
        or stat.S_IMODE(parent_value.st_mode) & 0o022
    ):
        raise ReleaseApprovalError("release_approval_output_invalid")
    target = parent / output.name
    if os.path.lexists(target):
        raise ReleaseApprovalError("release_approval_output_exists")
    payload = _canonical_json(value) + b"\n"
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=parent)
        temporary = Path(name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, target, follow_symlinks=False)
        temporary.unlink()
        temporary = None
        directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except FileExistsError as exc:
        raise ReleaseApprovalError("release_approval_output_exists") from exc
    except OSError as exc:
        raise ReleaseApprovalError("release_approval_output_publish_failed") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _binding_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--rollback-manifest", required=True)
    parser.add_argument("--rollback-signature", required=True)
    parser.add_argument("--allowed-signers", required=True)
    parser.add_argument("--release-signer-identity", required=True)
    parser.add_argument("--rollback-signer-identity")
    parser.add_argument("--rollout-plan", required=True)
    parser.add_argument("--approval-id", required=True)
    parser.add_argument("--expires-at", required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--owner-signer-identity", required=True)
    parser.add_argument("--max-ttl-seconds", type=int, default=DEFAULT_MAX_TTL_SECONDS)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="verify release bindings without signing or mutation")
    _binding_arguments(plan)
    sign = commands.add_parser("sign", help="sign and atomically write the approval file")
    _binding_arguments(sign)
    sign.add_argument("--owner-signing-key", required=True)
    sign.add_argument("--output", required=True)
    sign.add_argument("--ssh-keygen", default=shutil.which("ssh-keygen") or "/usr/bin/ssh-keygen")
    submit = commands.add_parser("submit", help="verify and submit a signed approval to Home")
    submit.add_argument("--approval-file", required=True)
    submit.add_argument("--allowed-signers", required=True)
    submit.add_argument("--ssh-keygen", default=shutil.which("ssh-keygen") or "/usr/bin/ssh-keygen")
    submit.add_argument("--control-url")
    submit.add_argument("--timeout", type=float, default=10.0)
    return parser


def _bound_payload(args: argparse.Namespace) -> dict[str, Any]:
    allowed = Path(args.allowed_signers)
    verified = load_verified_release(
        Path(args.manifest),
        Path(args.signature),
        allowed,
        args.release_signer_identity,
    )
    rollback = load_verified_release(
        Path(args.rollback_manifest),
        Path(args.rollback_signature),
        allowed,
        args.rollback_signer_identity or args.release_signer_identity,
    )
    rollout_plan = load_bound_rollout_plan(Path(args.rollout_plan), verified.manifest)
    return build_approval_payload(
        verified=verified,
        rollback=rollback,
        rollout_plan=rollout_plan,
        approval_id=args.approval_id,
        expires_at=args.expires_at,
        nonce=args.nonce,
        owner_signer_identity=args.owner_signer_identity,
        max_ttl_seconds=args.max_ttl_seconds,
    )


def _summary(payload: dict[str, Any], *, status: str, writes_performed: bool) -> dict[str, Any]:
    return {
        "schema_version": CLI_SCHEMA,
        "status": status,
        "writes_performed": writes_performed,
        "approval_id": payload["approval_id"],
        "release_id": payload["release_id"],
        "manifest_digest": payload["manifest_digest"],
        "rollback_release_id": payload["rollback"]["release_id"],
        "rollout_plan": payload["rollout_plan"],
        "expires_at": payload["expires_at"],
        "payload_sha256": hashlib.sha256(canonical_owner_approval_bytes(payload)).hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command in {"plan", "sign"}:
            payload = _bound_payload(args)
            if args.command == "plan":
                print(json.dumps(_summary(payload, status="planned", writes_performed=False), sort_keys=True))
                return 0
            signature = sign_approval_payload(
                payload,
                signing_key=Path(args.owner_signing_key),
                ssh_keygen=Path(args.ssh_keygen),
            )
            body = {**payload, "signature": signature}
            _publish_private_json(Path(args.output), body)
            result = _summary(payload, status="signed", writes_performed=True)
            result["output"] = str(Path(args.output))
            print(json.dumps(result, sort_keys=True))
            return 0

        body = _load_json_object(
            Path(args.approval_file),
            code="release_approval_file_invalid",
        )
        payload = verify_signed_approval(
            body,
            allowed_signers=Path(args.allowed_signers),
            ssh_keygen=Path(args.ssh_keygen),
        )
        client = ControlPlaneClient.from_environment(
            timeout=args.timeout,
            control_url=args.control_url,
        )
        record = client.request("POST", "/v1/approvals", body)
        if not isinstance(record, dict) or (
            record.get("approval_id") != payload["approval_id"]
            or record.get("release_id") != payload["release_id"]
            or str(record.get("status") or record.get("decision") or "").lower() != "approved"
        ):
            raise ReleaseApprovalError("release_approval_submit_response_invalid")
        print(json.dumps({
            "schema_version": CLI_SCHEMA,
            "status": "submitted",
            "writes_performed": True,
            "approval_id": payload["approval_id"],
            "release_id": payload["release_id"],
            "control_plane": "home",
        }, sort_keys=True))
        return 0
    except (ReleaseApprovalError, ReleaseError) as exc:
        code = exc.code if isinstance(exc, ReleaseApprovalError) else "release_approval_control_plane_failed"
        print(json.dumps({
            "schema_version": CLI_SCHEMA,
            "status": "failed",
            "error_type": code,
        }, sort_keys=True), file=sys.stderr)
        return 2
    except (OSError, ValueError, subprocess.SubprocessError):
        print(json.dumps({
            "schema_version": CLI_SCHEMA,
            "status": "failed",
            "error_type": "release_approval_failed",
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
