from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
)

from .database import get_database, transaction
from .identity import require_owner
from .normative_corpus import (
    PARSER_VERSION,
    FetchedNormative,
    NormativeCorpusError,
    NormativeFetcher,
    active_on,
    canonical_code,
    canonical_json,
    excerpt,
    fts_query,
    parse_normative_document,
    sha256_bytes,
    sha256_text,
    source_policy,
    store_sections,
)
from .product_access import ConstructionEstimateAccessDependency
from .schemas import UserSession
from .security import require_mutation_auth

router = APIRouter(prefix="/v1/normatives", tags=["normatives"])
DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
IdentityDependency = ConstructionEstimateAccessDependency
OwnerDependency = Annotated[UserSession, Depends(require_owner)]
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


IsoDateText = Annotated[
    str,
    StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$"),
]


class NormativeImportInput(ContractModel):
    code: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=500)
    document_kind: Literal[
        "sp",
        "snip",
        "gost",
        "methodology",
        "estimate_norm",
        "legal_act",
    ] = Field(alias="documentKind")
    edition_label: str = Field(alias="editionLabel", min_length=1, max_length=160)
    jurisdiction: str = Field(default="RU", min_length=2, max_length=64)
    authority: str = Field(min_length=1, max_length=240)
    authority_url: HttpUrl = Field(alias="authorityUrl", max_length=1_000)
    source_url: HttpUrl = Field(alias="sourceUrl", max_length=2_048)
    official_publication_url: HttpUrl | None = Field(
        default=None,
        alias="officialPublicationUrl",
        max_length=2_048,
    )
    effective_from: IsoDateText | None = Field(
        default=None,
        alias="effectiveFrom",
    )
    effective_to: IsoDateText | None = Field(
        default=None,
        alias="effectiveTo",
    )
    published_on: IsoDateText | None = Field(
        default=None,
        alias="publishedOn",
    )
    applicability: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormativeApprovalInput(ContractModel):
    status: Literal["effective", "superseded", "withdrawn"]
    verification_note: str = Field(
        alias="verificationNote",
        min_length=3,
        max_length=1_000,
    )


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _now(database: sqlite3.Connection) -> str:
    return str(
        database.execute(
            "SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
        ).fetchone()[0]
    )


def _audit(
    database: sqlite3.Connection,
    *,
    event_type: str,
    identity: UserSession,
    document_id: str | None,
    edition_id: str | None,
    payload: dict[str, Any],
    created_at: str,
) -> None:
    database.execute(
        """
        INSERT INTO normative_audit_events (
            id, event_type, document_id, edition_id,
            actor_tenant_id, actor_user_id, payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"norm_audit_{uuid.uuid4().hex}",
            event_type,
            document_id,
            edition_id,
            identity.tenant_id,
            identity.user_id,
            canonical_json(payload),
            created_at,
        ),
    )


def _fetcher(request: Request) -> NormativeFetcher:
    configured = getattr(request.app.state, "normative_fetcher", None)
    if configured is not None:
        return configured
    return NormativeFetcher()


@router.post(
    "/import-url",
    status_code=status.HTTP_201_CREATED,
)
def import_normative_url(
    payload: NormativeImportInput,
    request: Request,
    database: DatabaseDependency,
    identity: OwnerDependency,
    _auth: MutationAuthDependency,
) -> dict[str, Any]:
    source_url = str(payload.source_url)
    try:
        policy = source_policy(database, url=source_url)
        fetched: FetchedNormative = _fetcher(request).fetch(
            database,
            url=source_url,
        )
        final_policy = source_policy(database, url=fetched.final_url)
        text, sections = parse_normative_document(fetched)
    except NormativeCorpusError as exc:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "normative_import_rejected",
            str(exc),
        ) from exc

    code_key = canonical_code(payload.code)
    raw_hash = sha256_bytes(fetched.content)
    existing = database.execute(
        """
        SELECT editions.id, editions.status, documents.id AS document_id
        FROM normative_editions AS editions
        JOIN normative_documents AS documents
          ON documents.id = editions.document_id
        WHERE documents.canonical_code = ?
          AND editions.edition_label = ?
          AND editions.raw_sha256 = ?
        LIMIT 1
        """,
        (code_key, payload.edition_label, raw_hash),
    ).fetchone()
    if existing is not None:
        return {
            "documentId": str(existing["document_id"]),
            "editionId": str(existing["id"]),
            "status": str(existing["status"]),
            "duplicate": True,
            "rawSha256": raw_hash,
        }

    now = _now(database)
    document = database.execute(
        """
        SELECT id
        FROM normative_documents
        WHERE canonical_code = ?
        LIMIT 1
        """,
        (code_key,),
    ).fetchone()
    document_id = (
        str(document["id"])
        if document is not None
        else f"norm_document_{uuid.uuid4().hex}"
    )
    edition_id = f"norm_edition_{uuid.uuid4().hex}"
    policy_json = {
        "origin": str(final_policy["origin"]),
        "authority": str(final_policy["authority"]),
        "policyVersion": str(final_policy["policy_version"]),
        "storageAllowed": bool(final_policy["storage_allowed"]),
        "indexingAllowed": bool(final_policy["indexing_allowed"]),
        "excerptDisplayAllowed": bool(
            final_policy["excerpt_display_allowed"]
        ),
        "reviewStatus": str(final_policy["review_status"]),
        "termsUrl": final_policy["terms_url"],
    }
    metadata = {
        **payload.metadata,
        "requestedSourceUrl": source_url,
        "finalSourceUrl": fetched.final_url,
        "etag": fetched.etag,
        "lastModified": fetched.last_modified,
        "sectionCount": len(sections),
        "sourcePolicyOriginChanged": str(policy["origin"])
        != str(final_policy["origin"]),
    }
    with transaction(database, immediate=True):
        if document is None:
            database.execute(
                """
                INSERT INTO normative_documents (
                    id, canonical_code, display_code, title, document_kind,
                    jurisdiction, authority, authority_url, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    code_key,
                    payload.code,
                    payload.title,
                    payload.document_kind,
                    payload.jurisdiction,
                    payload.authority,
                    str(payload.authority_url),
                    now,
                    now,
                ),
            )
        else:
            database.execute(
                """
                UPDATE normative_documents
                SET display_code = ?, title = ?, document_kind = ?,
                    jurisdiction = ?, authority = ?, authority_url = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    payload.code,
                    payload.title,
                    payload.document_kind,
                    payload.jurisdiction,
                    payload.authority,
                    str(payload.authority_url),
                    now,
                    document_id,
                ),
            )
        database.execute(
            """
            INSERT INTO normative_editions (
                id, document_id, edition_label, status, source_url,
                official_publication_url, source_origin, effective_from,
                effective_to, published_on, fetched_at, media_type,
                parser_version, raw_sha256, raw_size, raw_content,
                extracted_text_sha256, source_policy_version,
                source_policy_json, metadata_json, verified_at,
                verified_by_user_id, verification_note, created_at
            ) VALUES (
                ?, ?, ?, 'candidate', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, NULL, NULL, NULL, ?
            )
            """,
            (
                edition_id,
                document_id,
                payload.edition_label,
                fetched.final_url,
                (
                    str(payload.official_publication_url)
                    if payload.official_publication_url is not None
                    else None
                ),
                str(final_policy["origin"]),
                payload.effective_from,
                payload.effective_to,
                payload.published_on,
                now,
                fetched.media_type,
                PARSER_VERSION,
                raw_hash,
                len(fetched.content),
                fetched.content,
                sha256_text(text),
                str(final_policy["policy_version"]),
                canonical_json(policy_json),
                canonical_json(metadata),
                now,
            ),
        )
        if int(final_policy["indexing_allowed"]) == 1:
            store_sections(
                database,
                edition_id=edition_id,
                document_code=payload.code,
                document_title=payload.title,
                sections=sections,
                applicability=payload.applicability,
            )
        _audit(
            database,
            event_type="normative_edition_imported",
            identity=identity,
            document_id=document_id,
            edition_id=edition_id,
            payload={
                "rawSha256": raw_hash,
                "sourceOrigin": str(final_policy["origin"]),
                "sectionCount": len(sections),
                "status": "candidate",
            },
            created_at=now,
        )
    return {
        "documentId": document_id,
        "editionId": edition_id,
        "status": "candidate",
        "duplicate": False,
        "rawSha256": raw_hash,
        "sectionCount": len(sections),
    }


@router.post("/editions/{edition_id}/status")
def set_normative_edition_status(
    edition_id: str,
    payload: NormativeApprovalInput,
    database: DatabaseDependency,
    identity: OwnerDependency,
    _auth: MutationAuthDependency,
) -> dict[str, Any]:
    edition = database.execute(
        """
        SELECT editions.*, policies.review_status,
               policies.indexing_allowed, documents.display_code
        FROM normative_editions AS editions
        JOIN normative_source_policies AS policies
          ON policies.origin = editions.source_origin
        JOIN normative_documents AS documents
          ON documents.id = editions.document_id
        WHERE editions.id = ?
        LIMIT 1
        """,
        (edition_id,),
    ).fetchone()
    if edition is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "normative_edition_not_found",
            "Редакция нормативного документа не найдена.",
        )
    if (
        payload.status == "effective"
        and (
            str(edition["review_status"]) in {"restricted", "blocked"}
            or int(edition["indexing_allowed"]) != 1
        )
    ):
        raise _error(
            status.HTTP_409_CONFLICT,
            "normative_source_policy_blocked",
            "Политика источника не разрешает использовать эту редакцию.",
        )
    if payload.status == "effective" and not edition["effective_from"]:
        raise _error(
            status.HTTP_409_CONFLICT,
            "normative_effective_date_required",
            "Для действующей редакции нужна дата начала действия.",
        )

    now = _now(database)
    with transaction(database, immediate=True):
        if payload.status == "effective":
            database.execute(
                """
                UPDATE normative_editions
                SET status = 'superseded'
                WHERE document_id = ? AND id <> ? AND status = 'effective'
                """,
                (edition["document_id"], edition_id),
            )
        database.execute(
            """
            UPDATE normative_editions
            SET status = ?, verified_at = ?, verified_by_user_id = ?,
                verification_note = ?
            WHERE id = ?
            """,
            (
                payload.status,
                now,
                identity.user_id,
                payload.verification_note,
                edition_id,
            ),
        )
        _audit(
            database,
            event_type="normative_edition_status_changed",
            identity=identity,
            document_id=str(edition["document_id"]),
            edition_id=edition_id,
            payload={
                "status": payload.status,
                "verificationNote": payload.verification_note,
            },
            created_at=now,
        )
    return {
        "editionId": edition_id,
        "documentCode": str(edition["display_code"]),
        "status": payload.status,
        "verifiedAt": now,
    }


@router.get("/search")
def search_normatives(
    database: DatabaseDependency,
    _identity: IdentityDependency,
    q: Annotated[str, Query(min_length=2, max_length=240)],
    as_of: Annotated[date, Query(alias="asOf")] = date.today(),
    document_kind: Annotated[
        Literal[
            "sp",
            "snip",
            "gost",
            "methodology",
            "estimate_norm",
            "legal_act",
        ]
        | None,
        Query(alias="documentKind"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=30)] = 12,
) -> dict[str, Any]:
    try:
        match = fts_query(q)
    except ValueError as exc:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_normative_query",
            "Запрос не содержит слов для поиска.",
        ) from exc
    predicates = [
        "normative_sections_fts MATCH ?",
        "editions.status = 'effective'",
        "(editions.effective_from IS NULL OR editions.effective_from <= ?)",
        "(editions.effective_to IS NULL OR editions.effective_to >= ?)",
        "policies.indexing_allowed = 1",
        "policies.excerpt_display_allowed = 1",
    ]
    parameters: list[Any] = [match, as_of.isoformat(), as_of.isoformat()]
    if document_kind is not None:
        predicates.append("documents.document_kind = ?")
        parameters.append(document_kind)
    parameters.append(limit)
    rows = database.execute(
        f"""
        SELECT sections.id AS section_id, sections.locator,
               sections.heading, sections.body, sections.body_sha256,
               sections.applicability_json,
               editions.id AS edition_id, editions.edition_label,
               editions.status, editions.source_url,
               editions.official_publication_url,
               editions.effective_from, editions.effective_to,
               editions.raw_sha256, editions.source_policy_version,
               documents.id AS document_id, documents.display_code,
               documents.title, documents.document_kind,
               documents.jurisdiction, documents.authority,
               bm25(normative_sections_fts) AS rank
        FROM normative_sections_fts
        JOIN normative_sections AS sections
          ON sections.id = normative_sections_fts.section_id
        JOIN normative_editions AS editions
          ON editions.id = sections.edition_id
        JOIN normative_documents AS documents
          ON documents.id = editions.document_id
        JOIN normative_source_policies AS policies
          ON policies.origin = editions.source_origin
        WHERE {' AND '.join(predicates)}
        ORDER BY rank ASC, documents.display_code ASC, sections.ordinal ASC
        LIMIT ?
        """,
        parameters,
    ).fetchall()
    results = []
    for row in rows:
        is_active = active_on(
            status=str(row["status"]),
            effective_from=row["effective_from"],
            effective_to=row["effective_to"],
            as_of=as_of,
        )
        if not is_active:
            continue
        results.append(
            {
                "evidenceId": (
                    f"{row['edition_id']}:{row['section_id']}:"
                    f"{row['body_sha256']}"
                ),
                "documentId": str(row["document_id"]),
                "documentCode": str(row["display_code"]),
                "documentTitle": str(row["title"]),
                "documentKind": str(row["document_kind"]),
                "editionId": str(row["edition_id"]),
                "editionLabel": str(row["edition_label"]),
                "locator": str(row["locator"]),
                "heading": str(row["heading"]),
                "excerpt": excerpt(str(row["body"]), q),
                "jurisdiction": str(row["jurisdiction"]),
                "authority": str(row["authority"]),
                "effectiveFrom": row["effective_from"],
                "effectiveTo": row["effective_to"],
                "sourceUrl": str(
                    row["official_publication_url"] or row["source_url"]
                ),
                "rawSha256": str(row["raw_sha256"]),
                "sectionSha256": str(row["body_sha256"]),
                "sourcePolicyVersion": str(row["source_policy_version"]),
                "applicability": json.loads(row["applicability_json"]),
                "status": "effective",
            }
        )
    return {
        "query": q,
        "asOf": as_of.isoformat(),
        "authorityClass": "official_normative",
        "results": results,
    }


@router.get("/documents/{document_code}/editions")
def list_normative_editions(
    document_code: str,
    database: DatabaseDependency,
    _identity: IdentityDependency,
) -> dict[str, Any]:
    try:
        code_key = canonical_code(document_code)
    except ValueError as exc:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_normative_code",
            "Некорректный код нормативного документа.",
        ) from exc
    document = database.execute(
        """
        SELECT *
        FROM normative_documents
        WHERE canonical_code = ?
        LIMIT 1
        """,
        (code_key,),
    ).fetchone()
    if document is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "normative_document_not_found",
            "Нормативный документ не найден.",
        )
    editions = database.execute(
        """
        SELECT id, edition_label, status, source_url,
               official_publication_url, effective_from, effective_to,
               published_on, fetched_at, media_type, parser_version,
               raw_sha256, raw_size, source_policy_version, verified_at,
               verification_note
        FROM normative_editions
        WHERE document_id = ?
        ORDER BY COALESCE(effective_from, '') DESC, fetched_at DESC, id DESC
        """,
        (document["id"],),
    ).fetchall()
    return {
        "document": {
            "id": str(document["id"]),
            "code": str(document["display_code"]),
            "title": str(document["title"]),
            "documentKind": str(document["document_kind"]),
            "jurisdiction": str(document["jurisdiction"]),
            "authority": str(document["authority"]),
            "authorityUrl": str(document["authority_url"]),
        },
        "editions": [
            {
                "id": str(row["id"]),
                "editionLabel": str(row["edition_label"]),
                "status": str(row["status"]),
                "sourceUrl": str(
                    row["official_publication_url"] or row["source_url"]
                ),
                "effectiveFrom": row["effective_from"],
                "effectiveTo": row["effective_to"],
                "publishedOn": row["published_on"],
                "fetchedAt": str(row["fetched_at"]),
                "mediaType": str(row["media_type"]),
                "parserVersion": str(row["parser_version"]),
                "rawSha256": str(row["raw_sha256"]),
                "rawSize": int(row["raw_size"]),
                "sourcePolicyVersion": str(row["source_policy_version"]),
                "verifiedAt": row["verified_at"],
                "verificationNote": row["verification_note"],
            }
            for row in editions
        ],
    }
