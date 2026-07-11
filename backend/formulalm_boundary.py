"""Durable FormulaLM learning intake and promotion boundary.

The request path may enqueue a trace, but it never trains a model or mutates
production weights.  A separate worker claims sanitized queue items and turns
them into candidates.  Promotion is an explicit, evidence-gated state machine.

This module intentionally has no FastAPI dependency.  HTTP authentication and
principal binding live in :mod:`execution_api`; this layer owns durable policy,
idempotency and state transitions.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BOUNDARY_SCHEMA_VERSION = "kolibri.formulalm-boundary.v1"
SCANNER_VERSION = "kolibri.formulalm-scanner.v1"
ALLOWED_CONSENT = {"explicit", "contractual", "public-permitted"}
ALLOWED_LICENSE = {"permitted"}
TRAINING_RETENTION = {"training-approved"}
QUEUE_STATES = {"queued", "processing", "candidate", "rejected", "failed"}
PROMOTION_TRANSITIONS: dict[str, set[str]] = {
    "candidate": {"training", "rejected"},
    "training": {"evaluating", "rejected"},
    "evaluating": {"canary-1", "rejected"},
    "canary-1": {"canary-10", "rolled-back"},
    "canary-10": {"canary-50", "rolled-back"},
    "canary-50": {"production", "rolled-back"},
    "production": {"rolled-back"},
    "rejected": set(),
    "rolled-back": set(),
}

_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "bot_token",
    "client_secret",
    "cookie",
    "credential",
    "credentials",
    "jwt",
    "passwd",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "secret_key",
    "session_cookie",
    "ssh_key",
    "token",
    "webhook_secret",
    "aws_secret_access_key",
}
_SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|ghp|github_pat|xox[baprs])-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
    re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?"
        r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        re.IGNORECASE,
    ),
    re.compile(
        r"[?&](?:access_token|api[_-]?key|auth|key|password|secret|sig|signature|token)="
        r"[^&#\s]+",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:access_token|api[_-]?key|authorization|password|secret|token)\s*[:=]\s*"
        r"[^\s,;&]+",
        re.IGNORECASE,
    ),
)
_PII_PATTERNS = (
    ("email", re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.IGNORECASE)),
    ("phone", re.compile(r"(?<!\d)(?:\+?7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)")),
    ("russian_passport", re.compile(r"(?<!\d)\d{4}[\s-]?\d{6}(?!\d)")),
    ("snils", re.compile(r"(?<!\d)\d{3}[- ]?\d{3}[- ]?\d{3}[ -]?\d{2}(?!\d)")),
)
_PAYMENT_CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)")
_CANONICAL_SHA256 = re.compile(r"^sha256:[a-f0-9]{64}$")
_SAFE_OPAQUE_IDENTIFIER_KEYS = {
    "actor_id",
    "artifact_id",
    "candidate_id",
    "event_id",
    "intake_id",
    "principal",
    "response_id",
    "source_response_id",
    "source_trace_id",
    "task_id",
    "trace_id",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _request_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalized_key(value: Any) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value).strip())
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _is_sensitive_key(value: Any) -> bool:
    normalized = _normalized_key(value)
    return normalized in _SENSITIVE_KEYS or normalized.endswith(
        (
            "_access_token",
            "_api_key",
            "_authorization",
            "_client_secret",
            "_cookie",
            "_password",
            "_private_key",
            "_refresh_token",
            "_secret",
            "_session_cookie",
            "_ssh_key",
            "_token",
            "_webhook_secret",
        )
    )


def _luhn_valid(value: str) -> bool:
    digits = [int(char) for char in value if char.isdigit()]
    if len(digits) < 13 or len(digits) > 19 or len(set(digits)) == 1:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


@dataclass(frozen=True)
class ScanResult:
    sanitized: Any
    report: dict[str, Any]

    @property
    def rejected(self) -> bool:
        return bool(self.report["secret_findings"] or self.report["pii_findings"])


class FormulaLMPolicyError(ValueError):
    """Policy or state-machine rejection safe to expose as a normalized code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class FormulaLMConflictError(ValueError):
    """Idempotency or state conflict safe to expose as a normalized code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class FormulaLMNotFoundError(LookupError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def scan_learning_payload(value: Any) -> ScanResult:
    """Scan and redact a value without retaining matched material.

    The sanitized value is useful for an accepted trace.  Any secret or PII
    finding still rejects the trace from the learning queue; redaction is a
    defense-in-depth guarantee for audit handling, not permission to train.
    """

    report: dict[str, Any] = {
        "schema_version": SCANNER_VERSION,
        "status": "passed",
        "secret_findings": 0,
        "pii_findings": 0,
        "secret_field_paths": [],
        "pii_field_paths": [],
        "pii_categories": [],
        "secret_material_persisted": False,
        "pii_material_persisted": False,
    }

    def walk(item: Any, *, key: str | None = None, path: tuple[str, ...] = ()) -> Any:
        current_segments = (*path, str(key)) if key is not None else path
        current_path = ".".join(current_segments)
        if key is not None and _is_sensitive_key(key):
            report["secret_findings"] += 1
            report["secret_field_paths"].append(current_path)
            return "[REDACTED]"
        if isinstance(item, dict):
            return {
                str(child_key): walk(child, key=str(child_key), path=current_segments)
                for child_key, child in item.items()
            }
        if isinstance(item, (list, tuple)):
            return [
                walk(child, path=(*current_segments, str(index)))
                for index, child in enumerate(item)
            ]
        if not isinstance(item, str):
            return item
        normalized_key = _normalized_key(key) if key is not None else ""
        if (
            normalized_key in _SAFE_OPAQUE_IDENTIFIER_KEYS
            and re.fullmatch(r"[A-Za-z0-9_.:-]{1,300}", item)
        ):
            return item
        if (
            normalized_key.endswith(("sha256", "digest", "content_hash"))
            and re.fullmatch(r"(?:sha256:)?[a-f0-9]{64}", item.lower())
        ):
            return item
        if (
            any(_normalized_key(segment) == "artifact_hashes" for segment in current_segments)
            and _CANONICAL_SHA256.fullmatch(item.lower())
        ):
            return item
        sanitized = item
        for pattern in _SECRET_PATTERNS:
            sanitized, count = pattern.subn("[REDACTED]", sanitized)
            if count:
                report["secret_findings"] += count
                report["secret_field_paths"].append(current_path or "$value")
        for category, pattern in _PII_PATTERNS:
            sanitized, count = pattern.subn("[REDACTED_PII]", sanitized)
            if count:
                report["pii_findings"] += count
                report["pii_field_paths"].append(current_path or "$value")
                report["pii_categories"].append(category)
        card_count = 0

        def redact_card(match: re.Match[str]) -> str:
            nonlocal card_count
            if not _luhn_valid(match.group(0)):
                return match.group(0)
            card_count += 1
            return "[REDACTED_PII]"

        sanitized = _PAYMENT_CARD_PATTERN.sub(redact_card, sanitized)
        if card_count:
            report["pii_findings"] += card_count
            report["pii_field_paths"].append(current_path or "$value")
            report["pii_categories"].append("payment_card")
        return sanitized

    sanitized = walk(value)
    if report["secret_findings"] or report["pii_findings"]:
        report["status"] = "rejected"
    report["secret_field_paths"] = sorted(set(report["secret_field_paths"]))
    report["pii_field_paths"] = sorted(set(report["pii_field_paths"]))
    report["pii_categories"] = sorted(set(report["pii_categories"]))
    return ScanResult(sanitized=sanitized, report=report)


def _policy_rejection(policy: dict[str, Any], quality: dict[str, Any]) -> str | None:
    consent = str(policy.get("consent") or "unknown")
    license_class = str(policy.get("license") or "unknown")
    retention = str(policy.get("retention_class") or "project")
    if consent not in ALLOWED_CONSENT:
        return "learning_consent_required"
    if license_class not in ALLOWED_LICENSE:
        return "learning_license_not_permitted"
    if retention not in TRAINING_RETENTION:
        return "learning_retention_not_training_approved"
    if str(quality.get("response_status") or "") != "completed":
        return "learning_response_not_completed"
    if str(quality.get("quality_verdict") or "") != "passed":
        return "learning_quality_not_passed"
    if str(quality.get("verifier_verdict") or "") != "passed":
        return "learning_verifier_not_passed"
    return None


def _validate_artifact_hashes(values: list[str]) -> list[str]:
    normalized = sorted(set(str(value).lower() for value in values))
    if any(not _CANONICAL_SHA256.fullmatch(value) for value in normalized):
        raise FormulaLMPolicyError("learning_artifact_hash_invalid")
    return normalized


class FormulaLMBoundary:
    """SQLite compatibility implementation of the FormulaLM boundary."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self._lock, self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS formulalm_intakes (
                    intake_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    source_trace_id TEXT NOT NULL,
                    source_response_id TEXT,
                    status TEXT NOT NULL,
                    rejection_code TEXT,
                    payload TEXT,
                    provenance TEXT NOT NULL,
                    policy TEXT NOT NULL,
                    quality TEXT NOT NULL,
                    artifact_hashes TEXT NOT NULL,
                    sanitization TEXT NOT NULL,
                    candidate_id TEXT,
                    claimed_by TEXT,
                    claimed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(scope, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_formulalm_intakes_status
                    ON formulalm_intakes(status, created_at, intake_id);
                CREATE TABLE IF NOT EXISTS formulalm_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    intake_id TEXT NOT NULL UNIQUE,
                    source_trace_id TEXT NOT NULL,
                    promotion_status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_formulalm_candidates_promotion
                    ON formulalm_candidates(promotion_status, created_at, candidate_id);
                CREATE TABLE IF NOT EXISTS formulalm_transition_events (
                    event_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    from_status TEXT NOT NULL,
                    to_status TEXT NOT NULL,
                    principal TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(candidate_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS formulalm_outbox (
                    outbox_id TEXT PRIMARY KEY,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    published_at TEXT
                );
                """
            )

    @staticmethod
    def _intake_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "schema_version": BOUNDARY_SCHEMA_VERSION,
            "id": row["intake_id"],
            "object": "learning_intake",
            "source_trace_id": row["source_trace_id"],
            "source_response_id": row["source_response_id"],
            "status": row["status"],
            "rejection_code": row["rejection_code"],
            "provenance": json.loads(row["provenance"]),
            "policy": json.loads(row["policy"]),
            "quality": json.loads(row["quality"]),
            "artifact_hashes": json.loads(row["artifact_hashes"]),
            "sanitization": json.loads(row["sanitization"]),
            "candidate_id": row["candidate_id"],
            "claimed_by": row["claimed_by"],
            "claimed_at": row["claimed_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "content_persisted": row["payload"] is not None,
        }

    @staticmethod
    def _candidate_row(row: sqlite3.Row) -> dict[str, Any]:
        return json.loads(row["payload"])

    @staticmethod
    def _append_outbox(
        conn: sqlite3.Connection,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
        now: str,
    ) -> None:
        event = {
            "schema_version": "kolibri.formulalm-event.v1",
            "id": _new_id("flm_evt"),
            "type": event_type,
            "source": "formulalm-boundary",
            "subject": f"{aggregate_type}/{aggregate_id}",
            "occurred_at": now,
            "data": payload,
        }
        conn.execute(
            """INSERT INTO formulalm_outbox
               (outbox_id, aggregate_type, aggregate_id, event_type, payload, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (
                _new_id("flm_outbox"),
                aggregate_type,
                aggregate_id,
                event_type,
                _canonical_json(event),
                now,
            ),
        )

    def enqueue_trace(
        self,
        *,
        idempotency_key: str,
        source_trace_id: str,
        source_response_id: str | None,
        capability: str,
        trace: dict[str, Any],
        provenance: dict[str, Any],
        policy: dict[str, Any],
        quality: dict[str, Any],
        artifact_hashes: list[str],
    ) -> dict[str, Any]:
        """Persist a sanitized intake or a content-free rejection audit.

        No candidate is created here.  This is the only operation called from
        the customer response path.
        """

        if not idempotency_key or not source_trace_id or not capability:
            raise FormulaLMPolicyError("learning_trace_contract_invalid")
        if not str(provenance.get("actor") or "").strip() or not str(
            provenance.get("policy_version") or ""
        ).strip():
            raise FormulaLMPolicyError("learning_provenance_required")
        artifact_hashes = _validate_artifact_hashes(artifact_hashes)
        raw = {
            "trace": trace,
            "provenance": provenance,
            "policy": policy,
            "quality": quality,
            "capability": capability,
        }
        request_hash = _request_hash({**raw, "artifact_hashes": artifact_hashes})
        scan = scan_learning_payload(raw)
        rejection_code = _policy_rejection(policy, quality)
        if scan.rejected:
            rejection_code = (
                "learning_secret_detected"
                if scan.report["secret_findings"]
                else "learning_pii_detected"
            )
        status = "rejected" if rejection_code else "queued"
        intake_id = _new_id("lintake")
        now = _utc_now()
        scope = f"response:{source_response_id or source_trace_id}"
        sanitized = scan.sanitized
        safe_provenance = sanitized["provenance"]
        safe_policy = sanitized["policy"]
        safe_quality = sanitized["quality"]
        # A rejected intake stores no prompt, output, tool call or other trace
        # content.  Scanner counts and normalized policy metadata are enough for
        # audit and do not preserve the matched values.
        payload = None if rejection_code else _canonical_json({
            "schema_version": "kolibri.formulalm-trace.v1",
            "source_trace_id": source_trace_id,
            "source_response_id": source_response_id,
            "capability": capability,
            "trace": sanitized["trace"],
        })
        with self._lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """SELECT * FROM formulalm_intakes
                   WHERE scope = ? AND idempotency_key = ?""",
                (scope, idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_hash"] != request_hash:
                    raise FormulaLMConflictError("learning_idempotency_conflict")
                return self._intake_row(existing)
            conn.execute(
                """INSERT INTO formulalm_intakes
                   (intake_id, scope, idempotency_key, request_hash, source_trace_id,
                    source_response_id, status, rejection_code, payload, provenance,
                    policy, quality, artifact_hashes, sanitization, candidate_id,
                    claimed_by, claimed_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)""",
                (
                    intake_id,
                    scope,
                    idempotency_key,
                    request_hash,
                    source_trace_id,
                    source_response_id,
                    status,
                    rejection_code,
                    payload,
                    _canonical_json(safe_provenance),
                    _canonical_json(safe_policy),
                    _canonical_json(safe_quality),
                    _canonical_json(artifact_hashes),
                    _canonical_json(scan.report),
                    now,
                    now,
                ),
            )
            self._append_outbox(
                conn,
                aggregate_type="learning_intake",
                aggregate_id=intake_id,
                event_type=f"learning.intake.{status}",
                payload={"status": status, "rejection_code": rejection_code},
                now=now,
            )
            row = conn.execute(
                "SELECT * FROM formulalm_intakes WHERE intake_id = ?", (intake_id,)
            ).fetchone()
            return self._intake_row(row)

    def get_intake(self, intake_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM formulalm_intakes WHERE intake_id = ?", (intake_id,)
            ).fetchone()
        if not row:
            raise FormulaLMNotFoundError("learning_intake_not_found")
        return self._intake_row(row)

    def list_intakes(self, *, status: str | None = None) -> list[dict[str, Any]]:
        if status is not None and status not in QUEUE_STATES:
            raise FormulaLMPolicyError("learning_intake_status_invalid")
        query = "SELECT * FROM formulalm_intakes"
        params: tuple[Any, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY created_at, intake_id"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._intake_row(row) for row in rows]

    def process_pending(self, *, worker_id: str, limit: int = 10) -> dict[str, Any]:
        """Claim queued traces and create candidates outside the request path."""

        if not worker_id or limit < 1 or limit > 100:
            raise FormulaLMPolicyError("learning_worker_contract_invalid")
        processed: list[dict[str, Any]] = []
        for _ in range(limit):
            with self._lock, self.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """SELECT * FROM formulalm_intakes WHERE status = 'queued'
                       ORDER BY created_at, intake_id LIMIT 1"""
                ).fetchone()
                if not row:
                    break
                intake_id = row["intake_id"]
                now = _utc_now()
                conn.execute(
                    """UPDATE formulalm_intakes
                       SET status = 'processing', claimed_by = ?, claimed_at = ?, updated_at = ?
                       WHERE intake_id = ? AND status = 'queued'""",
                    (worker_id, now, now, intake_id),
                )
                trace_payload = json.loads(row["payload"])
                provenance = json.loads(row["provenance"])
                policy = json.loads(row["policy"])
                quality = json.loads(row["quality"])
                artifact_hashes = json.loads(row["artifact_hashes"])
                scan_report = json.loads(row["sanitization"])
                candidate_id = _new_id("lcand")
                candidate = {
                    "schema_version": "kolibri.learning-candidate.v1",
                    "id": candidate_id,
                    "candidate_id": candidate_id,
                    "object": "learning_candidate",
                    "intake_id": intake_id,
                    "source_trace_id": row["source_trace_id"],
                    "source_response_id": row["source_response_id"],
                    "capability": trace_payload["capability"],
                    "artifact_hashes": artifact_hashes,
                    "consent": policy["consent"],
                    "license": policy["license"],
                    "retention_class": policy["retention_class"],
                    "data_classification": policy.get("data_classification", "internal"),
                    "sanitization": {
                        "status": "passed",
                        "redacted_fields": [],
                        "scanner_version": scan_report["schema_version"],
                        "reason": None,
                    },
                    "sanitization_report": scan_report,
                    "quality_verdict": quality["quality_verdict"],
                    "verifier_verdict": quality["verifier_verdict"],
                    "credit_assignment": quality.get("credit_assignment", {}),
                    "provenance": provenance,
                    "trace": trace_payload["trace"],
                    "promotion_status": "candidate",
                    "requires_eval": True,
                    "training_eligible": True,
                    "auto_promote": False,
                    "request_path_training": False,
                    "production_weight_mutation": False,
                    "created_at": now,
                    "updated_at": now,
                }
                conn.execute(
                    """INSERT INTO formulalm_candidates
                       (candidate_id, intake_id, source_trace_id, promotion_status, payload, created_at, updated_at)
                       VALUES (?, ?, ?, 'candidate', ?, ?, ?)""",
                    (candidate_id, intake_id, row["source_trace_id"], _canonical_json(candidate), now, now),
                )
                conn.execute(
                    """UPDATE formulalm_intakes
                       SET status = 'candidate', candidate_id = ?, updated_at = ?
                       WHERE intake_id = ?""",
                    (candidate_id, now, intake_id),
                )
                self._append_outbox(
                    conn,
                    aggregate_type="learning_candidate",
                    aggregate_id=candidate_id,
                    event_type="learning.candidate.created",
                    payload={"intake_id": intake_id, "promotion_status": "candidate"},
                    now=now,
                )
                processed.append(candidate)
        return {
            "schema_version": BOUNDARY_SCHEMA_VERSION,
            "worker_id": worker_id,
            "processed_count": len(processed),
            "candidates": processed,
            "production_weight_mutation": False,
            "auto_promote": False,
        }

    def get_candidate(self, candidate_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM formulalm_candidates WHERE candidate_id = ?", (candidate_id,)
            ).fetchone()
        if not row:
            raise FormulaLMNotFoundError("learning_candidate_not_found")
        return self._candidate_row(row)

    def list_candidates(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM formulalm_candidates ORDER BY created_at, candidate_id"
            ).fetchall()
        return [self._candidate_row(row) for row in rows]

    @staticmethod
    def _validate_transition_evidence(
        *, from_status: str, to_status: str, evidence: dict[str, Any], reason: str | None
    ) -> dict[str, Any]:
        scan = scan_learning_payload(evidence)
        if scan.rejected:
            raise FormulaLMPolicyError("learning_transition_evidence_sensitive")
        safe = scan.sanitized

        def require_digest(name: str) -> None:
            if not _CANONICAL_SHA256.fullmatch(str(safe.get(name) or "")):
                raise FormulaLMPolicyError(f"learning_{name}_required")

        if to_status == "training":
            require_digest("dataset_sha256")
            if not str(safe.get("training_run_id") or "").strip():
                raise FormulaLMPolicyError("learning_training_run_id_required")
        elif to_status == "evaluating":
            require_digest("model_artifact_sha256")
            if safe.get("training_verdict") != "passed":
                raise FormulaLMPolicyError("learning_training_verdict_required")
        elif to_status == "canary-1":
            require_digest("eval_report_sha256")
            if safe.get("independent_eval_verdict") != "passed":
                raise FormulaLMPolicyError("learning_independent_eval_required")
            if safe.get("eval_council_independent") is not True:
                raise FormulaLMPolicyError("learning_independent_eval_council_required")
        elif to_status in {"canary-10", "canary-50"}:
            require_digest("canary_report_sha256")
            if safe.get("canary_verdict") != "passed":
                raise FormulaLMPolicyError("learning_canary_verdict_required")
            if safe.get("external_fallback_retained") is not True:
                raise FormulaLMPolicyError("learning_external_fallback_required")
        elif to_status == "production":
            require_digest("canary_report_sha256")
            require_digest("release_manifest_sha256")
            if safe.get("canary_verdict") != "passed":
                raise FormulaLMPolicyError("learning_canary_verdict_required")
            if safe.get("external_fallback_retained") is not True:
                raise FormulaLMPolicyError("learning_external_fallback_required")
            if not str(safe.get("owner_approval_id") or "").strip():
                raise FormulaLMPolicyError("learning_owner_approval_required")
        elif to_status == "rejected":
            if not reason:
                raise FormulaLMPolicyError("learning_rejection_reason_required")
        elif to_status == "rolled-back":
            if from_status not in {"canary-1", "canary-10", "canary-50", "production"}:
                raise FormulaLMPolicyError("learning_rollback_source_invalid")
            if not reason or not str(safe.get("rollback_target") or "").strip():
                raise FormulaLMPolicyError("learning_rollback_evidence_required")
            if safe.get("external_fallback_retained") is not True:
                raise FormulaLMPolicyError("learning_external_fallback_required")
        return safe

    def transition_candidate(
        self,
        *,
        candidate_id: str,
        idempotency_key: str,
        to_status: str,
        principal: str,
        evidence: dict[str, Any],
        reason: str | None,
    ) -> dict[str, Any]:
        if to_status not in PROMOTION_TRANSITIONS:
            raise FormulaLMPolicyError("learning_promotion_status_invalid")
        transition_request = {
            "to_status": to_status,
            "principal": principal,
            "evidence": evidence,
            "reason": reason,
        }
        request_hash = _request_hash(transition_request)
        with self._lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM formulalm_candidates WHERE candidate_id = ?", (candidate_id,)
            ).fetchone()
            if not row:
                raise FormulaLMNotFoundError("learning_candidate_not_found")
            candidate = self._candidate_row(row)
            existing = conn.execute(
                """SELECT request_hash FROM formulalm_transition_events
                   WHERE candidate_id = ? AND idempotency_key = ?""",
                (candidate_id, idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_hash"] != request_hash:
                    raise FormulaLMConflictError("learning_transition_idempotency_conflict")
                return candidate
            from_status = str(candidate["promotion_status"])
            if to_status not in PROMOTION_TRANSITIONS.get(from_status, set()):
                raise FormulaLMConflictError(
                    f"learning_transition_invalid:{from_status}->{to_status}"
                )
            safe_evidence = self._validate_transition_evidence(
                from_status=from_status,
                to_status=to_status,
                evidence=evidence,
                reason=reason,
            )
            now = _utc_now()
            candidate["promotion_status"] = to_status
            candidate["updated_at"] = now
            candidate["last_transition"] = {
                "from_status": from_status,
                "to_status": to_status,
                "principal": principal,
                "reason": reason,
                "evidence": safe_evidence,
                "occurred_at": now,
            }
            candidate["auto_promote"] = False
            candidate["production_weight_mutation"] = False
            if to_status == "rolled-back":
                candidate["rollback"] = {
                    "target": safe_evidence["rollback_target"],
                    "reason": reason,
                    "external_fallback_retained": True,
                    "occurred_at": now,
                }
            conn.execute(
                """UPDATE formulalm_candidates
                   SET promotion_status = ?, payload = ?, updated_at = ?
                   WHERE candidate_id = ?""",
                (to_status, _canonical_json(candidate), now, candidate_id),
            )
            conn.execute(
                """INSERT INTO formulalm_transition_events
                   (event_id, candidate_id, idempotency_key, request_hash, from_status,
                    to_status, principal, evidence, reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _new_id("flm_transition"),
                    candidate_id,
                    idempotency_key,
                    request_hash,
                    from_status,
                    to_status,
                    principal,
                    _canonical_json(safe_evidence),
                    reason,
                    now,
                ),
            )
            self._append_outbox(
                conn,
                aggregate_type="learning_candidate",
                aggregate_id=candidate_id,
                event_type="learning.candidate.transitioned",
                payload={"from_status": from_status, "to_status": to_status},
                now=now,
            )
            return candidate

    def list_transition_events(self, candidate_id: str) -> list[dict[str, Any]]:
        self.get_candidate(candidate_id)
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT * FROM formulalm_transition_events
                   WHERE candidate_id = ? ORDER BY created_at, event_id""",
                (candidate_id,),
            ).fetchall()
        return [
            {
                "schema_version": "kolibri.formulalm-transition.v1",
                "id": row["event_id"],
                "candidate_id": row["candidate_id"],
                "from_status": row["from_status"],
                "to_status": row["to_status"],
                "principal": row["principal"],
                "evidence": json.loads(row["evidence"]),
                "reason": row["reason"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def status(self) -> dict[str, Any]:
        with self.connect() as conn:
            intake_rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM formulalm_intakes GROUP BY status"
            ).fetchall()
            promotion_rows = conn.execute(
                """SELECT promotion_status, COUNT(*) AS count
                   FROM formulalm_candidates GROUP BY promotion_status"""
            ).fetchall()
            pending_outbox = int(
                conn.execute(
                    "SELECT COUNT(*) FROM formulalm_outbox WHERE status = 'pending'"
                ).fetchone()[0]
            )
        return {
            "schema_version": BOUNDARY_SCHEMA_VERSION,
            "mode": "candidate-only",
            "intakes_by_status": {row["status"]: row["count"] for row in intake_rows},
            "candidates_by_promotion_status": {
                row["promotion_status"]: row["count"] for row in promotion_rows
            },
            "pending_outbox": pending_outbox,
            "request_path_training": False,
            "production_weight_mutation": False,
            "auto_promote": False,
            "promotion_requires_explicit_transition": True,
        }
