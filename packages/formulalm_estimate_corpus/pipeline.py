"""End-to-end FormulaLM estimate local-candidate builder and verifier.

The resulting bundle is integrity-protected but intentionally unapproved for
training.  A candidate-builder signature must never be interpreted as owner,
rights, budget, or model-promotion approval.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .integrity import (
    CANDIDATE_SIGNATURE_NAMESPACE,
    CANDIDATE_SIGNER_IDENTITY,
    CandidateIntegrityError,
    canonical_document_bytes,
    read_canonical_snapshot,
    sign_and_verify_candidate,
    verify_candidate_signature,
)
from .normalization import (
    canonical_json_bytes,
    decimal_eval_rows,
    learning_view,
    normalize_record,
    sha256_value,
)
from .policy import CorpusPolicyError
from .split import split_records


DEFAULT_MAX_RECORDS = 10_000
CANDIDATE_MANIFEST_VERSION = "2.0.0"
CANDIDATE_STATE = "unapproved_local_candidate"
EXPECTED_ARTIFACT_NAMES = frozenset(
    {
        "restricted_normalized_records",
        "train_learning",
        "eval_learning",
        "decimal_boundary_eval",
        "dedup_report",
        "stats",
        "evaluation_report",
    }
)
FORBIDDEN_TRAINING_FIELDS = frozenset(
    {"quantity", "unit_price", "line_total", "subtotal", "tax", "grand_total"}
)


class CorpusBuildError(RuntimeError):
    """Fail-closed corpus build error with no raw record content."""


@dataclass(frozen=True)
class LocalCandidateBuildResult:
    manifest_path: Path
    signature_path: Path
    manifest_sha256: str
    candidate_id: str
    input_records: int
    unique_records: int
    duplicate_records: int
    train_records: int
    eval_records: int

    def as_dict(self) -> dict[str, object]:
        return {
            "manifest_path": str(self.manifest_path),
            "signature_path": str(self.signature_path),
            "manifest_sha256": self.manifest_sha256,
            "candidate_id": self.candidate_id,
            "candidate_state": CANDIDATE_STATE,
            "training_authorized": False,
            "input_records": self.input_records,
            "unique_records": self.unique_records,
            "duplicate_records": self.duplicate_records,
            "train_records": self.train_records,
            "eval_records": self.eval_records,
        }


def _read_jsonl(path: Path, max_records: int) -> tuple[list[object], bytes]:
    if not path.is_file() or path.is_symlink():
        raise CorpusBuildError(f"input does not exist: {path}")
    try:
        raw_bytes = path.read_bytes()
        raw_text = raw_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CorpusBuildError("input snapshot is not readable UTF-8") from exc
    records: list[object] = []
    for line_number, line in enumerate(raw_text.splitlines(), start=1):
        if not line.strip():
            continue
        if len(records) >= max_records:
            raise CorpusBuildError(
                f"input exceeds candidate capacity of {max_records} records"
            )
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise CorpusBuildError(
                f"invalid JSON at input line {line_number}: {exc.msg}"
            ) from exc
    if not records:
        raise CorpusBuildError("input corpus is empty")
    return records, raw_bytes


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _jsonl_bytes(records: list[dict[str, object]]) -> bytes:
    return b"".join(canonical_json_bytes(record) + b"\n" for record in records)


def _write_artifact(
    root: Path,
    relative_path: str,
    content: bytes,
    *,
    record_count: int | None = None,
    training_eligible: bool,
) -> dict[str, object]:
    target = root / relative_path
    _atomic_write_bytes(target, content)
    artifact: dict[str, object] = {
        "path": relative_path,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "training_eligible": training_eligible,
    }
    if record_count is not None:
        artifact["records"] = record_count
    return artifact


def _safe_record_id(raw: object, index: int) -> str:
    if isinstance(raw, dict) and isinstance(raw.get("record_id"), str):
        value = raw["record_id"].strip()
        if value and len(value) <= 128:
            return value
    return f"input-index-{index}"


def _deduplicate(
    records: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    unique: list[dict[str, object]] = []
    duplicates: list[dict[str, str]] = []
    by_document: dict[str, dict[str, object]] = {}
    by_semantic: dict[str, dict[str, object]] = {}
    for record in sorted(records, key=lambda item: str(item["record_id"])):
        document_hash = str(record["provenance"]["document_sha256"])
        semantic_hash = str(record["dedup_sha256"])
        existing_document = by_document.get(document_hash)
        if existing_document is not None:
            if existing_document["dedup_sha256"] != semantic_hash:
                raise CorpusBuildError(
                    "same provenance.document_sha256 produced conflicting normalized content"
                )
            duplicates.append(
                {
                    "record_id": str(record["record_id"]),
                    "kept_record_id": str(existing_document["record_id"]),
                    "reason": "document_sha256",
                }
            )
            continue
        existing_semantic = by_semantic.get(semantic_hash)
        if existing_semantic is not None:
            duplicates.append(
                {
                    "record_id": str(record["record_id"]),
                    "kept_record_id": str(existing_semantic["record_id"]),
                    "reason": "normalized_estimate_sha256",
                }
            )
            by_document[document_hash] = existing_semantic
            continue
        unique.append(record)
        by_document[document_hash] = record
        by_semantic[semantic_hash] = record
    return unique, duplicates


def _counter(records: list[dict[str, object]], path: tuple[str, ...]) -> dict[str, int]:
    result: Counter[str] = Counter()
    for record in records:
        value: Any = record
        for part in path:
            value = value[part]
        result[str(value)] += 1
    return dict(sorted(result.items()))


def _record_hash_is_valid(record: dict[str, object]) -> bool:
    expected = record.get("record_sha256")
    payload = dict(record)
    payload.pop("record_sha256", None)
    return expected == sha256_value(payload)


def _hashed_learning_view(record: dict[str, object]) -> dict[str, object]:
    view = learning_view(record)
    view["learning_record_sha256"] = sha256_value(view)
    return view


def _learning_hash_is_valid(record: dict[str, object]) -> bool:
    expected = record.get("learning_record_sha256")
    payload = dict(record)
    payload.pop("learning_record_sha256", None)
    return expected == sha256_value(payload)


def _record_set_sha256(records: list[dict[str, object]]) -> str:
    return sha256_value(sorted(str(record["record_sha256"]) for record in records))


def _content_root_sha256(
    files: dict[str, dict[str, object]],
    *,
    source_snapshot: dict[str, object],
    record_set_sha256: str,
) -> str:
    return sha256_value(
        {
            "artifact_descriptors": files,
            "record_set_sha256": record_set_sha256,
            "source_snapshot": source_snapshot,
        }
    )


def _forbidden_fields(value: object, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_TRAINING_FIELDS:
                found.append(child_path)
            found.extend(_forbidden_fields(nested, child_path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found.extend(_forbidden_fields(nested, f"{path}[{index}]"))
    return found


def build_local_candidate(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    signing_key: str | Path,
    eval_ratio: float = 0.2,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> LocalCandidateBuildResult:
    """Build a signed, fail-closed, leakage-safe local candidate.

    This function never downloads data and does not grant training approval.
    It checks locally supplied rights/provenance declarations, then emits a
    signed candidate whose every artifact is marked training-ineligible.
    """

    if max_records < 1 or max_records > DEFAULT_MAX_RECORDS:
        raise CorpusBuildError(f"max_records must be between 1 and {DEFAULT_MAX_RECORDS}")
    if not 0 < eval_ratio < 1:
        raise CorpusBuildError("eval_ratio must be between 0 and 1")

    source_path = Path(input_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    candidate_signing_key = Path(signing_key).expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise CorpusBuildError("output directory must not already contain files")

    raw_records, source_bytes = _read_jsonl(source_path, max_records)
    normalized: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    for index, raw in enumerate(raw_records, start=1):
        try:
            normalized.append(normalize_record(raw))
        except (CorpusPolicyError, TypeError, KeyError) as exc:
            rejected.append(
                {
                    "input_index": index,
                    "record_id": _safe_record_id(raw, index),
                    "error": str(exc),
                }
            )
    if rejected:
        summary = "; ".join(
            f"{item['record_id']}: {item['error']}" for item in rejected[:10]
        )
        remainder = len(rejected) - 10
        if remainder > 0:
            summary += f"; and {remainder} more"
        raise CorpusBuildError(f"corpus rejected {len(rejected)} record(s): {summary}")

    unique, duplicates = _deduplicate(normalized)
    train_records, eval_records, split_report = split_records(unique, eval_ratio)
    if split_report["project_overlap"] or split_report["source_group_overlap"]:
        raise CorpusBuildError("project/source-group leakage detected")

    train_views = [_hashed_learning_view(record) for record in train_records]
    eval_views = [_hashed_learning_view(record) for record in eval_records]
    for view in train_views + eval_views:
        forbidden = _forbidden_fields(view)
        if forbidden:
            raise CorpusBuildError(
                f"Decimal calculator boundary violation: {', '.join(forbidden)}"
            )
    decimal_rows = [row for record in unique for row in decimal_eval_rows(record)]

    destination.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, object]] = {}
    files["restricted_normalized_records"] = _write_artifact(
        destination,
        "restricted/normalized-records.jsonl",
        _jsonl_bytes(unique),
        record_count=len(unique),
        training_eligible=False,
    )
    files["train_learning"] = _write_artifact(
        destination,
        "splits/train.learning.jsonl",
        _jsonl_bytes(train_views),
        record_count=len(train_views),
        training_eligible=False,
    )
    files["eval_learning"] = _write_artifact(
        destination,
        "splits/eval.learning.jsonl",
        _jsonl_bytes(eval_views),
        record_count=len(eval_views),
        training_eligible=False,
    )
    files["decimal_boundary_eval"] = _write_artifact(
        destination,
        "eval/decimal-boundary.jsonl",
        _jsonl_bytes(decimal_rows),
        record_count=len(decimal_rows),
        training_eligible=False,
    )
    files["dedup_report"] = _write_artifact(
        destination,
        "reports/dedup.jsonl",
        _jsonl_bytes(duplicates),
        record_count=len(duplicates),
        training_eligible=False,
    )

    stats = {
        "input_records": len(raw_records),
        "accepted_records_before_dedup": len(normalized),
        "unique_records": len(unique),
        "duplicate_records": len(duplicates),
        "rejected_records": 0,
        "estimate_lines": sum(len(record["estimate"]["lines"]) for record in unique),
        "train_records": len(train_views),
        "eval_records": len(eval_views),
        "rights_basis": _counter(unique, ("rights", "basis")),
        "access_class": _counter(unique, ("source", "access_class")),
        "region_code": _counter(unique, ("geography", "region_code")),
        "estimate_status": _counter(unique, ("estimate", "status")),
        "project_count": len({record["project_id"] for record in unique}),
        "source_group_count": len({record["source_group_id"] for record in unique}),
    }
    files["stats"] = _write_artifact(
        destination,
        "reports/stats.json",
        canonical_json_bytes(stats) + b"\n",
        training_eligible=False,
    )

    evaluation_report = {
        "schema_version": "1.0.0",
        "record_hashes_valid": all(_record_hash_is_valid(record) for record in unique),
        "line_arithmetic_valid": len(decimal_rows),
        "line_arithmetic_invalid": 0,
        "project_overlap": split_report["project_overlap"],
        "source_group_overlap": split_report["source_group_overlap"],
        "trainer_decimal_fields_found": 0,
        "source_evidence_coverage": "1",
        "note": "Decimal rows are verifier fixtures and are not trainer input.",
    }
    files["evaluation_report"] = _write_artifact(
        destination,
        "reports/evaluation.json",
        canonical_json_bytes(evaluation_report) + b"\n",
        training_eligible=False,
    )

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    source_snapshot = {
        "sha256": hashlib.sha256(source_bytes).hexdigest(),
        "bytes": len(source_bytes),
        "records": len(raw_records),
    }
    record_set_sha256 = _record_set_sha256(unique)
    candidate_identity = {
        "manifest_version": CANDIDATE_MANIFEST_VERSION,
        "record_set_sha256": record_set_sha256,
        "source_snapshot_sha256": source_snapshot["sha256"],
    }
    candidate_id = f"sha256:{sha256_value(candidate_identity)}"
    content_root_sha256 = _content_root_sha256(
        files,
        source_snapshot=source_snapshot,
        record_set_sha256=record_set_sha256,
    )
    manifest = {
        "manifest_version": CANDIDATE_MANIFEST_VERSION,
        "candidate_id": candidate_id,
        "created_at": generated_at,
        "candidate_contract": "local_candidate_integrity_only",
        "authorization": {
            "state": CANDIDATE_STATE,
            "training_authorized": False,
            "approval": None,
            "required_next_gate": "separately_signed_data_and_training_approval",
        },
        "integrity": {
            "signature_required": True,
            "signature_format": "sshsig",
            "signer_identity": CANDIDATE_SIGNER_IDENTITY,
            "namespace": CANDIDATE_SIGNATURE_NAMESPACE,
            "trust_root_policy": "fixed_root_owned_allowed_signers",
        },
        "purpose": (
            "Local FormulaLM estimate candidate preparation and evaluation; "
            "not training authorization"
        ),
        "candidate_records": len(unique),
        "capacity_limit_records": DEFAULT_MAX_RECORDS,
        "collection_complete": False,
        "source_acquisition": "provided_snapshot_only_no_network_fetch",
        "source_snapshot": source_snapshot,
        "record_set_sha256": record_set_sha256,
        "content_root_sha256": content_root_sha256,
        "schemas": {
            "record": (
                "packages/formulalm_estimate_corpus/schemas/"
                "estimate-corpus-record.schema.json"
            ),
            "manifest": (
                "packages/formulalm_estimate_corpus/schemas/"
                "estimate-corpus-manifest.schema.json"
            ),
        },
        "calculator_boundary": {
            "trained": False,
            "engine": "deterministic_decimal",
            "candidate_learning_views": [
                "splits/train.learning.jsonl",
                "splits/eval.learning.jsonl",
            ],
            "training_authorized": False,
            "excluded_fields": sorted(FORBIDDEN_TRAINING_FIELDS),
            "eval_only_file": "eval/decimal-boundary.jsonl",
        },
        "split_policy": {
            "method": "connected_components_by_project_or_source_group",
            "eval_ratio_requested": eval_ratio,
            "component_count": split_report["component_count"],
            "project_overlap": split_report["project_overlap"],
            "source_group_overlap": split_report["source_group_overlap"],
        },
        "stats": stats,
        "files": files,
    }
    manifest_path = destination / "manifest.json"
    manifest_bytes = canonical_document_bytes(manifest)
    _atomic_write_bytes(manifest_path, manifest_bytes)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    _atomic_write_bytes(
        destination / "manifest.sha256.json",
        canonical_document_bytes(
            {
                "manifest": "manifest.json",
                "sha256": manifest_sha256,
                "signature": "manifest.json.sig",
                "signature_namespace": CANDIDATE_SIGNATURE_NAMESPACE,
                "signer_identity": CANDIDATE_SIGNER_IDENTITY,
            }
        ),
    )
    try:
        signature_path = sign_and_verify_candidate(
            manifest_path,
            manifest_bytes=manifest_bytes,
            signing_key=candidate_signing_key,
        )
        verification = verify_local_candidate(manifest_path)
    except CandidateIntegrityError as exc:
        raise CorpusBuildError(str(exc)) from exc
    if verification["status"] != "pass":
        raise CorpusBuildError(f"post-build verification failed: {verification}")
    return LocalCandidateBuildResult(
        manifest_path=manifest_path,
        signature_path=signature_path,
        manifest_sha256=manifest_sha256,
        candidate_id=candidate_id,
        input_records=len(raw_records),
        unique_records=len(unique),
        duplicate_records=len(duplicates),
        train_records=len(train_views),
        eval_records=len(eval_views),
    )


def _load_jsonl_bytes(content: bytes, label: str) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CorpusBuildError(f"non-UTF-8 JSONL artifact {label}") from exc
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CorpusBuildError(
                f"invalid JSONL in {label} at line {line_number}"
            ) from exc
        if not isinstance(value, dict):
            raise CorpusBuildError(f"non-object JSONL record in {label}")
        result.append(value)
    return result


def _manifest_artifact_path(root: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise CorpusBuildError("manifest artifact path is invalid")
    if "\\" in relative:
        raise CorpusBuildError("manifest artifact path is invalid")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise CorpusBuildError("manifest artifact path is invalid")
    unresolved = root.joinpath(*pure.parts)
    cursor = root
    for part in pure.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise CorpusBuildError("manifest artifact symlink is forbidden")
    candidate = unresolved.resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise CorpusBuildError("manifest artifact path escapes corpus root") from exc
    return candidate


def _validate_manifest_contract(manifest: dict[str, object]) -> None:
    expected_keys = {
        "manifest_version",
        "candidate_id",
        "created_at",
        "candidate_contract",
        "authorization",
        "integrity",
        "purpose",
        "candidate_records",
        "capacity_limit_records",
        "collection_complete",
        "source_acquisition",
        "source_snapshot",
        "record_set_sha256",
        "content_root_sha256",
        "schemas",
        "calculator_boundary",
        "split_policy",
        "stats",
        "files",
    }
    if set(manifest) != expected_keys:
        raise CorpusBuildError("candidate_manifest_contract_keys_invalid")
    if manifest.get("manifest_version") != CANDIDATE_MANIFEST_VERSION:
        raise CorpusBuildError("candidate_manifest_version_invalid")
    if manifest.get("candidate_contract") != "local_candidate_integrity_only":
        raise CorpusBuildError("candidate_contract_invalid")
    if manifest.get("authorization") != {
        "state": CANDIDATE_STATE,
        "training_authorized": False,
        "approval": None,
        "required_next_gate": "separately_signed_data_and_training_approval",
    }:
        raise CorpusBuildError("candidate_authorization_must_remain_unapproved")
    if manifest.get("integrity") != {
        "signature_required": True,
        "signature_format": "sshsig",
        "signer_identity": CANDIDATE_SIGNER_IDENTITY,
        "namespace": CANDIDATE_SIGNATURE_NAMESPACE,
        "trust_root_policy": "fixed_root_owned_allowed_signers",
    }:
        raise CorpusBuildError("candidate_integrity_policy_invalid")
    candidate_records = manifest.get("candidate_records")
    stats = manifest.get("stats")
    if not isinstance(stats, dict):
        raise CorpusBuildError("candidate_stats_invalid")
    stats_train_records = stats.get("train_records")
    stats_eval_records = stats.get("eval_records")
    if (
        not isinstance(candidate_records, int)
        or isinstance(candidate_records, bool)
        or not 1 <= candidate_records <= DEFAULT_MAX_RECORDS
        or manifest.get("capacity_limit_records") != DEFAULT_MAX_RECORDS
        or manifest.get("collection_complete") is not False
        or manifest.get("source_acquisition")
        != "provided_snapshot_only_no_network_fetch"
    ):
        raise CorpusBuildError("candidate_collection_claim_invalid")

    source_snapshot = manifest.get("source_snapshot")
    if not isinstance(source_snapshot, dict) or set(source_snapshot) != {
        "sha256",
        "bytes",
        "records",
    }:
        raise CorpusBuildError("candidate_source_snapshot_invalid")
    if (
        not isinstance(source_snapshot.get("sha256"), str)
        or len(str(source_snapshot["sha256"])) != 64
        or any(character not in "0123456789abcdef" for character in str(source_snapshot["sha256"]))
        or not isinstance(source_snapshot.get("bytes"), int)
        or source_snapshot["bytes"] < 1
        or not isinstance(stats.get("duplicate_records"), int)
        or isinstance(stats.get("duplicate_records"), bool)
        or stats["duplicate_records"] < 0
        or source_snapshot.get("records")
        != candidate_records + stats["duplicate_records"]
        or stats.get("input_records") != source_snapshot.get("records")
        or stats.get("unique_records") != candidate_records
        or not isinstance(stats_train_records, int)
        or isinstance(stats_train_records, bool)
        or not isinstance(stats_eval_records, int)
        or isinstance(stats_eval_records, bool)
        or stats_train_records + stats_eval_records != candidate_records
    ):
        raise CorpusBuildError("candidate_source_snapshot_invalid")

    for key in ("record_set_sha256", "content_root_sha256"):
        value = manifest.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise CorpusBuildError(f"candidate_{key}_invalid")

    expected_candidate_id = f"sha256:{sha256_value({
        'manifest_version': CANDIDATE_MANIFEST_VERSION,
        'record_set_sha256': manifest['record_set_sha256'],
        'source_snapshot_sha256': source_snapshot['sha256'],
    })}"
    if manifest.get("candidate_id") != expected_candidate_id:
        raise CorpusBuildError("candidate_id_binding_invalid")

    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != EXPECTED_ARTIFACT_NAMES:
        raise CorpusBuildError("candidate_artifact_set_invalid")
    for name, artifact in files.items():
        if not isinstance(artifact, dict):
            raise CorpusBuildError(f"candidate_artifact_{name}_invalid")
        expected_descriptor_keys = {"path", "sha256", "bytes", "training_eligible"}
        if name not in {"stats", "evaluation_report"}:
            expected_descriptor_keys.add("records")
        if set(artifact) != expected_descriptor_keys:
            raise CorpusBuildError(f"candidate_artifact_{name}_descriptor_invalid")
        digest = artifact.get("sha256")
        if (
            artifact.get("training_eligible") is not False
            or not isinstance(artifact.get("path"), str)
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not isinstance(artifact.get("bytes"), int)
            or artifact["bytes"] < 0
            or (
                "records" in artifact
                and (
                    not isinstance(artifact["records"], int)
                    or isinstance(artifact["records"], bool)
                    or artifact["records"] < 0
                )
            )
        ):
            raise CorpusBuildError(f"candidate_artifact_{name}_descriptor_invalid")

    expected_content_root = _content_root_sha256(
        files,
        source_snapshot=source_snapshot,
        record_set_sha256=str(manifest["record_set_sha256"]),
    )
    if manifest.get("content_root_sha256") != expected_content_root:
        raise CorpusBuildError("candidate_content_root_binding_invalid")

    calculator_boundary = manifest.get("calculator_boundary")
    if not isinstance(calculator_boundary, dict) or (
        calculator_boundary.get("trained") is not False
        or calculator_boundary.get("training_authorized") is not False
        or calculator_boundary.get("engine") != "deterministic_decimal"
        or calculator_boundary.get("candidate_learning_views")
        != ["splits/train.learning.jsonl", "splits/eval.learning.jsonl"]
        or calculator_boundary.get("excluded_fields")
        != sorted(FORBIDDEN_TRAINING_FIELDS)
        or calculator_boundary.get("eval_only_file")
        != "eval/decimal-boundary.jsonl"
    ):
        raise CorpusBuildError("candidate_calculator_boundary_invalid")


def verify_local_candidate(manifest_path: str | Path) -> dict[str, object]:
    manifest_file = Path(manifest_path).expanduser().resolve()
    try:
        snapshot = read_canonical_snapshot(manifest_file)
        verify_candidate_signature(snapshot.raw, Path(f"{manifest_file}.sig"))
    except CandidateIntegrityError as exc:
        raise CorpusBuildError(str(exc)) from exc
    manifest = snapshot.payload
    _validate_manifest_contract(manifest)
    root = manifest_file.parent
    errors: list[str] = []

    checksum_path = root / "manifest.sha256.json"
    try:
        checksum_snapshot = read_canonical_snapshot(checksum_path)
    except CandidateIntegrityError as exc:
        errors.append(f"manifest checksum invalid: {exc}")
    else:
        expected_checksum = {
            "manifest": "manifest.json",
            "sha256": snapshot.sha256,
            "signature": "manifest.json.sig",
            "signature_namespace": CANDIDATE_SIGNATURE_NAMESPACE,
            "signer_identity": CANDIDATE_SIGNER_IDENTITY,
        }
        if checksum_snapshot.payload != expected_checksum:
            errors.append("manifest checksum binding mismatch")

    files = manifest.get("files")
    artifact_bytes: dict[str, bytes] = {}
    for name, artifact in files.items():
        relative = artifact.get("path")
        try:
            target = _manifest_artifact_path(root, relative)
        except CorpusBuildError as exc:
            errors.append(f"files.{name}.path is invalid: {exc}")
            continue
        try:
            content = target.read_bytes()
        except OSError:
            errors.append(f"missing artifact {relative}")
            continue
        artifact_bytes[name] = content
        if hashlib.sha256(content).hexdigest() != artifact.get("sha256"):
            errors.append(f"hash mismatch for {relative}")
        if len(content) != artifact.get("bytes"):
            errors.append(f"size mismatch for {relative}")

    required_for_semantics = {
        "train_learning",
        "eval_learning",
        "restricted_normalized_records",
        "decimal_boundary_eval",
    }
    if not required_for_semantics.issubset(artifact_bytes):
        return {
            "status": "fail",
            "manifest": str(manifest_file),
            "manifest_sha256": snapshot.sha256,
            "candidate_id": manifest.get("candidate_id"),
            "candidate_state": CANDIDATE_STATE,
            "training_authorized": False,
            "signature_verified": True,
            "errors": errors or ["required candidate artifacts are missing"],
        }
    train = _load_jsonl_bytes(artifact_bytes["train_learning"], "train_learning")
    evaluation = _load_jsonl_bytes(artifact_bytes["eval_learning"], "eval_learning")
    actual_record_counts = {
        "train_learning": len(train),
        "eval_learning": len(evaluation),
    }
    for label, records in (("train", train), ("eval", evaluation)):
        for record in records:
            forbidden = _forbidden_fields(record)
            if forbidden:
                errors.append(f"{label} contains Decimal fields: {forbidden[:3]}")
            if not _learning_hash_is_valid(record):
                errors.append(f"{label} contains invalid learning record hash")

    train_projects = {record["project_id"] for record in train}
    eval_projects = {record["project_id"] for record in evaluation}
    train_groups = {record["source_group_id"] for record in train}
    eval_groups = {record["source_group_id"] for record in evaluation}
    project_overlap = sorted(train_projects & eval_projects)
    group_overlap = sorted(train_groups & eval_groups)
    if project_overlap:
        errors.append(f"project leakage: {project_overlap}")
    if group_overlap:
        errors.append(f"source-group leakage: {group_overlap}")

    restricted = _load_jsonl_bytes(
        artifact_bytes["restricted_normalized_records"],
        "restricted_normalized_records",
    )
    actual_record_counts["restricted_normalized_records"] = len(restricted)
    invalid_hashes = [
        str(record.get("record_id"))
        for record in restricted
        if not _record_hash_is_valid(record)
    ]
    if invalid_hashes:
        errors.append(f"invalid record hashes: {invalid_hashes[:5]}")
    restricted_hashes = {str(record.get("record_sha256")) for record in restricted}
    learning_hashes = {
        str(record.get("record_sha256")) for record in train + evaluation
    }
    if not learning_hashes.issubset(restricted_hashes):
        errors.append("learning view references unknown restricted record hash")
    if _record_set_sha256(restricted) != manifest.get("record_set_sha256"):
        errors.append("record set digest mismatch")
    if len(restricted) != manifest.get("candidate_records"):
        errors.append("candidate record count mismatch")

    decimal_rows = _load_jsonl_bytes(
        artifact_bytes["decimal_boundary_eval"],
        "decimal_boundary_eval",
    )
    actual_record_counts["decimal_boundary_eval"] = len(decimal_rows)
    if "dedup_report" in artifact_bytes:
        actual_record_counts["dedup_report"] = len(
            _load_jsonl_bytes(artifact_bytes["dedup_report"], "dedup_report")
        )
    for name, actual_count in actual_record_counts.items():
        if files[name].get("records") != actual_count:
            errors.append(f"record count mismatch for {files[name]['path']}")
    if any(row.get("training_eligible") is not False for row in decimal_rows):
        errors.append("decimal evaluation row marked training eligible")

    return {
        "status": "pass" if not errors else "fail",
        "manifest": str(manifest_file),
        "manifest_sha256": snapshot.sha256,
        "candidate_id": manifest.get("candidate_id"),
        "candidate_state": CANDIDATE_STATE,
        "training_authorized": False,
        "signature_verified": True,
        "signer_identity": CANDIDATE_SIGNER_IDENTITY,
        "signature_namespace": CANDIDATE_SIGNATURE_NAMESPACE,
        "content_root_sha256": manifest.get("content_root_sha256"),
        "train_records": len(train),
        "eval_records": len(evaluation),
        "restricted_records": len(restricted),
        "decimal_eval_rows": len(decimal_rows),
        "project_overlap": project_overlap,
        "source_group_overlap": group_overlap,
        "errors": errors,
    }
