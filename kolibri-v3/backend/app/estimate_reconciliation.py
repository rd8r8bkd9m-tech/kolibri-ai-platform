"""Repair current estimate slots that used model price candidates.

Historical estimate versions remain immutable.  The repair appends a new
Estimate Engine version using the server-owned reference snapshot, marks the
previous current version stale, and records a dedicated audit event.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from .config import Settings
from .database import connect_database, initialize_database, transaction
from .estimate_artifact import parse_estimate_document
from .estimate_engine import (
    PlasteringScope,
    ProjectCaseRef,
    calculate_plastering_estimate,
    canonical_json,
)
from .estimate_engine_router import (
    PlasteringCalculationInput,
    PlasteringScopeInput,
    _scope,
    calculate_plastering,
)
from .reference_price_snapshot import (
    PLASTERING_REFERENCE_PRICE_SNAPSHOT_VERSION,
    plastering_reference_price_assumption,
    plastering_reference_price_quotes,
)
from .schemas import AgentProfile, UserRole, UserSession


REPAIR_POLICY_VERSION = "ai-candidate-arithmetic-repair/1.0.0"


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    project_id: str
    document_id: str
    previous_version: int
    replacement_version: int | None
    previous_total: str
    replacement_total: str | None
    status: str


def _stable_digest(*parts: object) -> str:
    return hashlib.sha256(
        "\x1f".join(str(part) for part in parts).encode("utf-8", "strict")
    ).hexdigest()


def _repair_key(row: sqlite3.Row) -> str:
    digest = _stable_digest(
        REPAIR_POLICY_VERSION,
        PLASTERING_REFERENCE_PRICE_SNAPSHOT_VERSION,
        row["tenant_id"],
        row["document_id"],
        row["version"],
    )
    return f"estimate-reconcile:{digest}"


def _repair_audit_id(row: sqlite3.Row) -> str:
    return "audit_estimate_reconcile_" + _stable_digest(
        REPAIR_POLICY_VERSION,
        row["tenant_id"],
        row["document_id"],
        row["version"],
    )[:32]


def _stale_candidate_history(database: sqlite3.Connection) -> None:
    groups = database.execute(
        """
        SELECT tenant_id, project_id, document_id,
               group_concat(version, ',') AS versions
        FROM (
            SELECT versions.tenant_id, versions.project_id,
                   versions.document_id, versions.version
            FROM estimate_versions AS versions
            WHERE EXISTS (
                SELECT 1
                FROM json_each(versions.content_json, '$.rows') AS rows
                WHERE json_extract(
                    rows.value,
                    '$.engine_price_provenance.sourceType'
                ) = 'ai_candidate'
            )
            ORDER BY versions.version
        )
        GROUP BY tenant_id, project_id, document_id
        ORDER BY tenant_id, project_id, document_id
        """
    ).fetchall()
    database.execute(
        """
        UPDATE estimate_versions
        SET status = 'stale'
        WHERE EXISTS (
            SELECT 1
            FROM json_each(estimate_versions.content_json, '$.rows') AS rows
            WHERE json_extract(
                rows.value,
                '$.engine_price_provenance.sourceType'
            ) = 'ai_candidate'
        )
        """
    )
    now = str(
        database.execute(
            "SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
        ).fetchone()[0]
    )
    for group in groups:
        versions = [
            int(value)
            for value in str(group["versions"] or "").split(",")
            if value
        ]
        audit_id = "audit_estimate_candidate_history_" + _stable_digest(
            REPAIR_POLICY_VERSION,
            group["tenant_id"],
            group["document_id"],
        )[:24]
        database.execute(
            """
            INSERT OR IGNORE INTO audit_events (
                tenant_id, id, actor_user_id, action, subject_type,
                subject_id, project_id, metadata_json, created_at
            ) VALUES (?, ?, NULL, 'estimate.price_authority_invalidated',
                      'estimate', ?, ?, ?, ?)
            """,
            (
                group["tenant_id"],
                audit_id,
                group["document_id"],
                group["project_id"],
                canonical_json(
                    {
                        "actorKind": "system_reconciliation",
                        "invalidatedVersions": versions,
                        "policyVersion": REPAIR_POLICY_VERSION,
                        "reason": (
                            "ai_candidate prices participated in "
                            "deterministic arithmetic"
                        ),
                    }
                ),
                now,
            ),
        )


def _candidate_slots(database: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        database.execute(
            """
            SELECT slots.tenant_id, slots.project_id,
                   slots.id AS document_id, slots.version,
                   slots.content_json, slots.updated_at,
                   versions.origin_type,
                   versions.created_by_user_id,
                   users.email, users.name, users.role,
                   users.preferred_agent_profile,
                   (
                       SELECT calculations.project_case_id
                       FROM estimate_calculations AS calculations
                       WHERE calculations.tenant_id = slots.tenant_id
                         AND calculations.document_id = slots.id
                         AND calculations.estimate_version = slots.version
                       ORDER BY calculations.created_at DESC,
                                calculations.id DESC
                       LIMIT 1
                   ) AS source_case_id,
                   (
                       SELECT calculations.project_case_version
                       FROM estimate_calculations AS calculations
                       WHERE calculations.tenant_id = slots.tenant_id
                         AND calculations.document_id = slots.id
                         AND calculations.estimate_version = slots.version
                       ORDER BY calculations.created_at DESC,
                                calculations.id DESC
                       LIMIT 1
                   ) AS source_case_version
            FROM document_slots AS slots
            JOIN estimate_versions AS versions
              ON versions.tenant_id = slots.tenant_id
             AND versions.document_id = slots.id
             AND versions.version = slots.version
            JOIN users
              ON users.id = versions.created_by_user_id
             AND users.tenant_id = versions.tenant_id
            WHERE slots.slot_type = 'estimate'
              AND slots.content_json IS NOT NULL
              AND versions.origin_type = 'engine_calculation'
              AND EXISTS (
                    SELECT 1
                    FROM json_each(slots.content_json, '$.rows') AS rows
                    WHERE json_extract(
                        rows.value,
                        '$.engine_price_provenance.sourceType'
                    ) = 'ai_candidate'
              )
            ORDER BY slots.tenant_id, slots.project_id
            """
        ).fetchall()
    )


def _source_case(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    case_id: str,
    case_version: int,
) -> sqlite3.Row:
    row = database.execute(
        """
        SELECT id, version, snapshot_json, source_message_id
        FROM project_cases
        WHERE tenant_id = ? AND project_id = ?
          AND id = ? AND version = ?
        LIMIT 1
        """,
        (tenant_id, project_id, case_id, case_version),
    ).fetchone()
    if row is None:
        raise RuntimeError(
            f"Source ProjectCase is missing for {project_id} "
            f"({case_id} v{case_version})"
        )
    return row


def _active_units(
    *,
    tenant_id: str,
    project_id: str,
    case_id: str,
    case_version: int,
    region: str,
    scope: PlasteringScope,
) -> dict[str, str]:
    preflight = calculate_plastering_estimate(
        project_case=ProjectCaseRef(
            tenant_id=tenant_id,
            project_id=project_id,
            case_id=case_id,
            version=case_version,
            region=region,
        ),
        scope=scope,
        prices=[],
    )
    return {
        str(item["code"]): str(item["unit"])
        for item in preflight["items"]
    }


def _append_repair_assumption(values: object) -> list[str]:
    assumptions = (
        [str(value) for value in values if str(value).strip()]
        if isinstance(values, list)
        else []
    )
    repair_assumption = plastering_reference_price_assumption()
    if repair_assumption not in assumptions:
        assumptions = assumptions[:19] + [repair_assumption]
    return assumptions[:20]


def _identity(row: sqlite3.Row) -> UserSession:
    return UserSession(
        user_id=str(row["created_by_user_id"]),
        tenant_id=str(row["tenant_id"]),
        role=UserRole(str(row["role"])),
        preferred_agent_profile=AgentProfile(
            str(row["preferred_agent_profile"])
        ),
        email=str(row["email"]),
        name=str(row["name"]),
    )


def _payload(
    database: sqlite3.Connection,
    row: sqlite3.Row,
) -> PlasteringCalculationInput:
    if row["source_case_id"] is None or row["source_case_version"] is None:
        raise RuntimeError(
            f"Source calculation lineage is missing for {row['project_id']}"
        )
    source_case = _source_case(
        database,
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        case_id=str(row["source_case_id"]),
        case_version=int(row["source_case_version"]),
    )
    snapshot = json.loads(str(source_case["snapshot_json"]))
    if not isinstance(snapshot, dict):
        raise RuntimeError(
            f"ProjectCase snapshot is invalid for {row['project_id']}"
        )
    scope_input = PlasteringScopeInput.model_validate(snapshot.get("scope"))
    region = str(snapshot.get("region") or "").strip()
    if not region:
        raise RuntimeError(f"Region is missing for {row['project_id']}")
    active_units = _active_units(
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        case_id=str(source_case["id"]),
        case_version=int(source_case["version"]),
        region=region,
        scope=_scope(scope_input),
    )
    document = parse_estimate_document(
        row["content_json"],
        now=str(row["updated_at"]),
    )
    return PlasteringCalculationInput.model_validate(
        {
            "expectedEstimateVersion": int(row["version"]),
            "region": region,
            "title": str(document["title"]),
            "assumptions": _append_repair_assumption(
                snapshot.get("assumptions")
            ),
            "scope": scope_input.model_dump(by_alias=True, mode="json"),
            "prices": plastering_reference_price_quotes(
                active_units=active_units,
                region=region,
            ),
            "terms": snapshot.get("commercialTerms") or {},
            "sourceMessageId": source_case["source_message_id"],
            "requireReleaseReady": False,
        }
    )


def _total(content_json: str | bytes | None) -> str:
    value = json.loads(str(content_json or "{}"))
    if not isinstance(value, dict):
        return "0.00"
    totals = value.get("totals")
    if not isinstance(totals, dict):
        return "0.00"
    return str(totals.get("total") or "0.00")


def reconcile_ai_candidate_estimates(
    database: sqlite3.Connection,
    *,
    apply: bool,
) -> list[ReconciliationResult]:
    results: list[ReconciliationResult] = []
    for row in _candidate_slots(database):
        previous_total = _total(row["content_json"])
        if not apply:
            results.append(
                ReconciliationResult(
                    project_id=str(row["project_id"]),
                    document_id=str(row["document_id"]),
                    previous_version=int(row["version"]),
                    replacement_version=None,
                    previous_total=previous_total,
                    replacement_total=None,
                    status="repair_required",
                )
            )
            continue

        payload = _payload(database, row)
        with transaction(database, immediate=True):
            response = calculate_plastering(
                str(row["project_id"]),
                payload,
                database,
                _identity(row),
                None,
                _repair_key(row),
            )
            replacement_version = int(response["estimateVersion"])
            replacement = database.execute(
                """
                SELECT content_json, created_at
                FROM estimate_versions
                WHERE tenant_id = ? AND document_id = ? AND version = ?
                LIMIT 1
                """,
                (
                    row["tenant_id"],
                    row["document_id"],
                    replacement_version,
                ),
            ).fetchone()
            if replacement is None:
                raise RuntimeError(
                    f"Replacement estimate is missing for {row['project_id']}"
                )
            replacement_total = _total(replacement["content_json"])
            database.execute(
                """
                UPDATE estimate_versions
                SET status = 'stale'
                WHERE tenant_id = ? AND document_id = ? AND version = ?
                """,
                (
                    row["tenant_id"],
                    row["document_id"],
                    row["version"],
                ),
            )
            calculated_audit = database.execute(
                """
                SELECT id, metadata_json
                FROM audit_events
                WHERE tenant_id = ?
                  AND action = 'estimate.calculated'
                  AND subject_type = 'estimate_calculation'
                  AND subject_id = ?
                LIMIT 1
                """,
                (row["tenant_id"], response["calculationId"]),
            ).fetchone()
            if calculated_audit is None:
                raise RuntimeError(
                    f"Calculation audit is missing for {row['project_id']}"
                )
            calculated_metadata = json.loads(
                str(calculated_audit["metadata_json"])
            )
            calculated_metadata["actorKind"] = "system_reconciliation"
            calculated_metadata["repairPolicyVersion"] = (
                REPAIR_POLICY_VERSION
            )
            database.execute(
                """
                UPDATE audit_events
                SET actor_user_id = NULL, metadata_json = ?
                WHERE tenant_id = ? AND id = ?
                """,
                (
                    canonical_json(calculated_metadata),
                    row["tenant_id"],
                    calculated_audit["id"],
                ),
            )
            database.execute(
                """
                INSERT OR IGNORE INTO audit_events (
                    tenant_id, id, actor_user_id, action, subject_type,
                    subject_id, project_id, metadata_json, created_at
                ) VALUES (?, ?, ?, 'estimate.price_authority_reconciled',
                          'estimate', ?, ?, ?, ?)
                """,
                (
                    row["tenant_id"],
                    _repair_audit_id(row),
                    None,
                    row["document_id"],
                    row["project_id"],
                    canonical_json(
                        {
                            "policyVersion": REPAIR_POLICY_VERSION,
                            "previousVersion": int(row["version"]),
                            "previousTotal": previous_total,
                            "replacementVersion": replacement_version,
                            "replacementTotal": replacement_total,
                            "actorKind": "system_reconciliation",
                            "originalCreatedByUserId": (
                                row["created_by_user_id"]
                            ),
                            "reason": (
                                "ai_candidate prices participated in "
                                "deterministic arithmetic"
                            ),
                        }
                    ),
                    replacement["created_at"],
                ),
            )
        results.append(
            ReconciliationResult(
                project_id=str(row["project_id"]),
                document_id=str(row["document_id"]),
                previous_version=int(row["version"]),
                replacement_version=replacement_version,
                previous_total=previous_total,
                replacement_total=replacement_total,
                status="repaired",
            )
        )
    if apply:
        with transaction(database, immediate=True):
            _stale_candidate_history(database)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Append corrected versions. Without this flag the command is read-only.",
    )
    arguments = parser.parse_args()
    settings = Settings.from_env()
    if arguments.apply:
        initialize_database(settings.database_url)
    database = connect_database(settings.database_url)
    try:
        results = reconcile_ai_candidate_estimates(
            database,
            apply=arguments.apply,
        )
        print(
            json.dumps(
                [asdict(result) for result in results],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    finally:
        database.close()


if __name__ == "__main__":
    main()
