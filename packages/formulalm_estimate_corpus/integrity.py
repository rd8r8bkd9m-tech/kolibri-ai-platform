"""Pinned OpenSSH integrity contract for FormulaLM local corpus candidates.

The signature identifies the local candidate builder and protects the exact
manifest bytes.  It is deliberately *not* a data-owner or model-training
approval.  Those are separate future gates.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .normalization import canonical_json_bytes


CANDIDATE_SIGNATURE_NAMESPACE = "kolibri-formulalm-estimate-corpus-candidate-v1"
CANDIDATE_SIGNER_IDENTITY = "kolibri-formulalm-estimate-corpus-candidate"
CANDIDATE_TRUST_ROOT = Path(
    "/etc/kolibri/trust/formulalm-estimate-corpus-candidate.allowed_signers"
)
TRUST_ROOT_REQUIRED_UID = 0


class CandidateIntegrityError(RuntimeError):
    """Fail-closed error without leaking signer material or command output."""


@dataclass(frozen=True)
class CanonicalSnapshot:
    path: Path
    payload: dict[str, Any]
    raw: bytes
    sha256: str


def canonical_document_bytes(payload: object) -> bytes:
    return canonical_json_bytes(payload) + b"\n"


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_canonical_snapshot(path: Path) -> CanonicalSnapshot:
    """Read and parse a canonical JSON file exactly once.

    Signature verification, digest calculation, and contract validation all
    use this same byte snapshot, avoiding a manifest read/verify/read race.
    """

    try:
        if path.is_symlink():
            raise CandidateIntegrityError("candidate_manifest_symlink_forbidden")
        raw = path.read_bytes()
        payload = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except CandidateIntegrityError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CandidateIntegrityError("candidate_manifest_unreadable") from exc
    if not isinstance(payload, dict) or raw != canonical_document_bytes(payload):
        raise CandidateIntegrityError("candidate_manifest_not_canonical")
    return CanonicalSnapshot(
        path=path,
        payload=payload,
        raw=raw,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def _signature_environment() -> dict[str, str]:
    result = {
        key: value
        for key, value in os.environ.items()
        if key in {"HOME", "LANG", "LC_ALL", "PATH", "TMPDIR"}
    }
    result["SSH_ASKPASS_REQUIRE"] = "never"
    result.pop("DISPLAY", None)
    return result


def _require_executable(name: str) -> str:
    binary = shutil.which(name)
    if not binary:
        raise CandidateIntegrityError("candidate_signature_tool_unavailable")
    return binary


def _require_pinned_trust_root() -> Path:
    """Return the fixed trust root only when protected by root ownership.

    The path, signer identity, and namespace are policy constants rather than
    CLI arguments.  A caller therefore cannot substitute its own public key.
    """

    path = CANDIDATE_TRUST_ROOT
    if not path.is_absolute():
        raise CandidateIntegrityError("candidate_trust_root_not_pinned")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise CandidateIntegrityError("candidate_trust_root_missing") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != TRUST_ROOT_REQUIRED_UID
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise CandidateIntegrityError("candidate_trust_root_permissions_invalid")
    return path


def verify_candidate_signature(
    content_bytes: bytes,
    signature_path: Path,
    *,
    ssh_keygen: str | None = None,
) -> None:
    allowed_signers = _require_pinned_trust_root()
    if not signature_path.is_file() or signature_path.is_symlink():
        raise CandidateIntegrityError("candidate_signature_material_missing")
    binary = ssh_keygen or _require_executable("ssh-keygen")
    try:
        result = subprocess.run(
            (
                binary,
                "-Y",
                "verify",
                "-f",
                str(allowed_signers),
                "-I",
                CANDIDATE_SIGNER_IDENTITY,
                "-n",
                CANDIDATE_SIGNATURE_NAMESPACE,
                "-s",
                str(signature_path),
            ),
            input=content_bytes,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_signature_environment(),
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CandidateIntegrityError(
            "candidate_signature_verification_unavailable"
        ) from exc
    if result.returncode != 0:
        raise CandidateIntegrityError("candidate_signature_verification_failed")


def sign_and_verify_candidate(
    manifest_path: Path,
    *,
    manifest_bytes: bytes,
    signing_key: Path,
    ssh_keygen: str | None = None,
) -> Path:
    """Sign a candidate manifest, then immediately verify pinned identity."""

    binary = ssh_keygen or _require_executable("ssh-keygen")
    try:
        metadata = signing_key.lstat()
    except OSError as exc:
        raise CandidateIntegrityError("candidate_signing_key_missing") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise CandidateIntegrityError("candidate_signing_key_permissions_invalid")
    signature_path = Path(f"{manifest_path}.sig")
    if signature_path.exists():
        raise CandidateIntegrityError("candidate_signature_already_exists")
    try:
        result = subprocess.run(
            (
                binary,
                "-Y",
                "sign",
                "-f",
                str(signing_key),
                "-n",
                CANDIDATE_SIGNATURE_NAMESPACE,
                str(manifest_path),
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_signature_environment(),
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CandidateIntegrityError("candidate_signature_tool_unavailable") from exc
    if result.returncode != 0 or not signature_path.is_file():
        raise CandidateIntegrityError("candidate_manifest_signing_failed")
    verify_candidate_signature(
        manifest_bytes,
        signature_path,
        ssh_keygen=binary,
    )
    return signature_path
