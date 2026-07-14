from __future__ import annotations

import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from packages.formulalm_estimate_corpus import (
    build_local_candidate,
    verify_local_candidate,
)
from packages.formulalm_estimate_corpus import integrity
from packages.formulalm_estimate_corpus.cli import main as corpus_cli
from packages.formulalm_estimate_corpus.integrity import (
    CANDIDATE_SIGNATURE_NAMESPACE,
    CANDIDATE_SIGNER_IDENTITY,
    CandidateIntegrityError,
    canonical_document_bytes,
)
from packages.formulalm_estimate_corpus.normalization import learning_view, normalize_record
from packages.formulalm_estimate_corpus.pipeline import CorpusBuildError
from packages.formulalm_estimate_corpus.policy import CorpusPolicyError


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/formulalm_estimate_corpus/approved-records.jsonl"
DECIMAL_FIELDS = {"quantity", "unit_price", "line_total", "subtotal", "tax", "grand_total"}


def _read_fixture() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _walk_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for nested in value.values() for key in _walk_keys(nested)
        }
    if isinstance(value, list):
        return {key for nested in value for key in _walk_keys(nested)}
    return set()


def _ssh_keygen() -> str:
    binary = shutil.which("ssh-keygen")
    if not binary:
        pytest.skip("ssh-keygen is unavailable")
    return binary


def _new_signer(root: Path, name: str) -> Path:
    key = root / name
    subprocess.run(
        (_ssh_keygen(), "-q", "-t", "ed25519", "-N", "", "-f", str(key)),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    key.chmod(0o600)
    return key


def _allowed_signers(path: Path, key: Path) -> Path:
    fields = Path(f"{key}.pub").read_text(encoding="utf-8").split()
    path.write_text(
        f"{CANDIDATE_SIGNER_IDENTITY} {fields[0]} {fields[1]}\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def _sign(path: Path, key: Path, namespace: str = CANDIDATE_SIGNATURE_NAMESPACE) -> Path:
    signature = Path(f"{path}.sig")
    signature.unlink(missing_ok=True)
    subprocess.run(
        (
            _ssh_keygen(),
            "-Y",
            "sign",
            "-f",
            str(key),
            "-n",
            namespace,
            str(path),
        ),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return signature


@pytest.fixture
def candidate_signer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    key = _new_signer(tmp_path, "candidate-builder")
    allowed = _allowed_signers(tmp_path / "candidate.allowed_signers", key)
    # Production uses the non-configurable root-owned path. Tests substitute
    # only the internal resolver; no CLI/API trust-root override exists.
    monkeypatch.setattr(integrity, "_require_pinned_trust_root", lambda: allowed)
    return key


def test_builds_signed_unapproved_local_candidate(
    tmp_path: Path, candidate_signer: Path
) -> None:
    result = build_local_candidate(
        FIXTURE,
        tmp_path / "candidate",
        signing_key=candidate_signer,
        eval_ratio=0.25,
    )

    assert result.input_records == 5
    assert result.unique_records == 4
    assert result.duplicate_records == 1
    assert result.train_records > 0
    assert result.eval_records > 0
    assert result.signature_path.is_file()

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["candidate_records"] == 4
    assert manifest["capacity_limit_records"] == 10_000
    assert manifest["collection_complete"] is False
    assert manifest["authorization"] == {
        "approval": None,
        "required_next_gate": "separately_signed_data_and_training_approval",
        "state": "unapproved_local_candidate",
        "training_authorized": False,
    }
    assert manifest["calculator_boundary"]["trained"] is False
    assert manifest["calculator_boundary"]["training_authorized"] is False
    assert all(
        artifact["training_eligible"] is False
        for artifact in manifest["files"].values()
    )
    assert "approval_id" not in manifest

    verification = verify_local_candidate(result.manifest_path)
    assert verification["status"] == "pass"
    assert verification["signature_verified"] is True
    assert verification["training_authorized"] is False
    assert verification["candidate_state"] == "unapproved_local_candidate"
    assert verification["errors"] == []


def test_cli_rejects_free_form_forged_approval_id(
    tmp_path: Path, candidate_signer: Path
) -> None:
    with pytest.raises(SystemExit):
        corpus_cli(
            [
                "build-local-candidate",
                "--input",
                str(FIXTURE),
                "--output",
                str(tmp_path / "candidate"),
                "--candidate-signing-key",
                str(candidate_signer),
                "--approval-id",
                "FORGED-APPROVAL",
            ]
        )


def test_forged_signer_cannot_promote_candidate(
    tmp_path: Path, candidate_signer: Path
) -> None:
    result = build_local_candidate(
        FIXTURE, tmp_path / "candidate", signing_key=candidate_signer
    )
    forged_key = _new_signer(tmp_path, "forged-builder")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    manifest["authorization"] = {
        "approval": "FORGED",
        "required_next_gate": "none",
        "state": "approved",
        "training_authorized": True,
    }
    result.manifest_path.write_bytes(canonical_document_bytes(manifest))
    _sign(result.manifest_path, forged_key)

    with pytest.raises(CorpusBuildError, match="signature_verification_failed"):
        verify_local_candidate(result.manifest_path)


def test_candidate_builder_signature_cannot_mint_training_approval(
    tmp_path: Path, candidate_signer: Path
) -> None:
    result = build_local_candidate(
        FIXTURE, tmp_path / "candidate", signing_key=candidate_signer
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    manifest["authorization"] = {
        "approval": "FORGED",
        "required_next_gate": "none",
        "state": "approved",
        "training_authorized": True,
    }
    result.manifest_path.write_bytes(canonical_document_bytes(manifest))
    _sign(result.manifest_path, candidate_signer)

    with pytest.raises(
        CorpusBuildError, match="candidate_authorization_must_remain_unapproved"
    ):
        verify_local_candidate(result.manifest_path)


def test_tampered_manifest_fails_signature(
    tmp_path: Path, candidate_signer: Path
) -> None:
    result = build_local_candidate(
        FIXTURE, tmp_path / "candidate", signing_key=candidate_signer
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    manifest["candidate_records"] = 9999
    result.manifest_path.write_bytes(canonical_document_bytes(manifest))

    with pytest.raises(CorpusBuildError, match="signature_verification_failed"):
        verify_local_candidate(result.manifest_path)


def test_wrong_signature_namespace_fails(
    tmp_path: Path, candidate_signer: Path
) -> None:
    result = build_local_candidate(
        FIXTURE, tmp_path / "candidate", signing_key=candidate_signer
    )
    _sign(result.manifest_path, candidate_signer, namespace="forged-namespace")

    with pytest.raises(CorpusBuildError, match="signature_verification_failed"):
        verify_local_candidate(result.manifest_path)


def test_tampered_restricted_record_fails_hashes(
    tmp_path: Path, candidate_signer: Path
) -> None:
    result = build_local_candidate(
        FIXTURE, tmp_path / "candidate", signing_key=candidate_signer
    )
    restricted = result.manifest_path.parent / "restricted/normalized-records.jsonl"
    rows = restricted.read_text(encoding="utf-8").splitlines()
    record = json.loads(rows[0])
    record["estimate"]["title"] = "Подменённая запись"
    rows[0] = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    restricted.write_text("\n".join(rows) + "\n", encoding="utf-8")

    verification = verify_local_candidate(result.manifest_path)
    assert verification["status"] == "fail"
    assert any(
        marker in error
        for error in verification["errors"]
        for marker in ("hash mismatch", "invalid record hashes", "record set digest")
    )


def test_manifest_checksum_tampering_fails(
    tmp_path: Path, candidate_signer: Path
) -> None:
    result = build_local_candidate(
        FIXTURE, tmp_path / "candidate", signing_key=candidate_signer
    )
    checksum = result.manifest_path.parent / "manifest.sha256.json"
    payload = json.loads(checksum.read_text(encoding="utf-8"))
    payload["sha256"] = "0" * 64
    checksum.write_bytes(canonical_document_bytes(payload))

    verification = verify_local_candidate(result.manifest_path)
    assert verification["status"] == "fail"
    assert "manifest checksum binding mismatch" in verification["errors"]


def test_learning_projection_cannot_train_decimal_calculator() -> None:
    normalized = normalize_record(_read_fixture()[0])
    projection = learning_view(normalized)

    assert not (DECIMAL_FIELDS & _walk_keys(projection))
    assert projection["calculator_boundary"]["engine"] == "deterministic_decimal"
    assert normalized["estimate"]["lines"][0]["line_total"] == "250.00"


def test_policy_rejects_private_or_unlicensed_input() -> None:
    record = deepcopy(_read_fixture()[0])
    record["source"]["access_class"] = "private"
    record["rights"]["training_allowed"] = False

    with pytest.raises(CorpusPolicyError, match="training_allowed"):
        normalize_record(record)


def test_policy_rejects_secret_like_material() -> None:
    record = deepcopy(_read_fixture()[0])
    record["estimate"]["scope_summary"] = "Bearer abcdefghijklmnopqrstuvwxyz123456"

    with pytest.raises(CorpusPolicyError, match="secret-like"):
        normalize_record(record)


def test_policy_rejects_pii_like_material() -> None:
    record = deepcopy(_read_fixture()[0])
    record["estimate"]["scope_summary"] = "Связаться: person@example.com"

    with pytest.raises(CorpusPolicyError, match="PII-like"):
        normalize_record(record)


def test_decimal_boundary_rejects_wrong_line_total() -> None:
    record = deepcopy(_read_fixture()[0])
    record["estimate"]["lines"][0]["line_total"] = "251.00"

    with pytest.raises(CorpusPolicyError, match="Decimal boundary"):
        normalize_record(record)


def test_candidate_id_is_deterministic_for_same_snapshot(
    tmp_path: Path, candidate_signer: Path
) -> None:
    first = build_local_candidate(
        FIXTURE, tmp_path / "first", signing_key=candidate_signer
    )
    second = build_local_candidate(
        FIXTURE, tmp_path / "second", signing_key=candidate_signer
    )

    assert first.candidate_id == second.candidate_id


def test_build_fails_closed_when_any_record_is_invalid(
    tmp_path: Path, candidate_signer: Path
) -> None:
    records = _read_fixture()
    records[1]["rights"]["allowed_uses"] = ["formula_lm_estimate_evaluation"]
    source = tmp_path / "invalid.jsonl"
    source.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )

    with pytest.raises(CorpusBuildError, match="rejected 1 record"):
        build_local_candidate(
            source, tmp_path / "candidate", signing_key=candidate_signer
        )


def test_pinned_trust_root_rejects_non_root_owned_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed = tmp_path / "attacker.allowed_signers"
    allowed.write_text("attacker ssh-ed25519 AAAA\n", encoding="utf-8")
    allowed.chmod(0o600)
    monkeypatch.setattr(integrity, "CANDIDATE_TRUST_ROOT", allowed)
    monkeypatch.setattr(
        integrity, "TRUST_ROOT_REQUIRED_UID", allowed.stat().st_uid + 1
    )

    with pytest.raises(CandidateIntegrityError, match="permissions_invalid"):
        integrity._require_pinned_trust_root()
