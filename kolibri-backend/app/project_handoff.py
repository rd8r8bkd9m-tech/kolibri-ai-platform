"""One-use, project-scoped continuity handoff between trusted surfaces."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.browser_session import validate_anonymous_session
from app.models import (
    DocumentDB,
    EstimateDB,
    OrganizationAuditEventDB,
    ProjectAccessDB,
    ProjectDB,
    ProjectHandoffDB,
    ProjectMessageDB,
    ProjectMessageMutationDB,
    PublicResponseDB,
)
from app.project_history import project_to_dict


HANDOFF_VERSION = 1
HANDOFF_TTL_SECONDS = max(
    60,
    min(int(os.getenv("KOLIBRI_PROJECT_HANDOFF_TTL_SECONDS", str(7 * 24 * 60 * 60))), 30 * 24 * 60 * 60),
)


class ProjectHandoffError(Exception):
    pass


class ProjectHandoffConfigurationError(ProjectHandoffError):
    pass


class ProjectHandoffNotFound(ProjectHandoffError):
    pass


class ProjectHandoffExpired(ProjectHandoffError):
    pass


class ProjectHandoffAlreadyClaimed(ProjectHandoffError):
    pass


class AnonymousAdoptionUnsupported(ProjectHandoffError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _handoff_signing_key() -> bytes:
    configured = os.getenv("KOLIBRI_PROJECT_HANDOFF_SECRET", "").strip()
    secret = configured.encode("utf-8")
    if len(secret) < 32 or configured.lower().startswith(("change-", "replace-", "generate-")):
        raise ProjectHandoffConfigurationError(
            "KOLIBRI_PROJECT_HANDOFF_SECRET must be a dedicated random secret of at least 32 bytes"
        )
    return secret


def validate_project_handoff_configuration() -> None:
    _handoff_signing_key()


def _token(project_id: str, idempotency_key: str, expires_at: datetime) -> str:
    expiry_epoch = int(_utc(expires_at).timestamp())
    message = f"{HANDOFF_VERSION}\0{project_id}\0{idempotency_key}\0{expiry_epoch}".encode("utf-8")
    digest = hmac.new(_handoff_signing_key(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def issue_project_handoff(
    db: Session,
    *,
    project_id: str,
    source_scope_id: str,
    idempotency_key: str,
) -> str:
    """Return a stable token for a live attempt and rotate an expired token."""

    project = db.query(ProjectDB).filter(
        ProjectDB.id == project_id,
        ProjectDB.scope_id == source_scope_id,
        ProjectDB.deleted_at.is_(None),
    ).first()
    if project is None:
        raise ProjectHandoffNotFound(project_id)

    now = _now()
    existing = db.query(ProjectHandoffDB).filter(
        ProjectHandoffDB.idempotency_key == idempotency_key,
    ).first()
    if existing is not None:
        if (
            existing.project_id != project_id
            or existing.source_scope_id != source_scope_id
        ):
            raise ProjectHandoffError("project handoff idempotency conflict")
        if existing.claimed_at is None and _utc(existing.expires_at) <= now:
            next_expiry = now + timedelta(seconds=HANDOFF_TTL_SECONDS)
            token = _token(project_id, idempotency_key, next_expiry)
            while hmac.compare_digest(existing.token_hash, _token_hash(token)):
                next_expiry += timedelta(seconds=1)
                token = _token(project_id, idempotency_key, next_expiry)
            existing.expires_at = next_expiry
            existing.token_hash = _token_hash(token)
            db.commit()
            return token
        token = _token(project_id, idempotency_key, existing.expires_at)
        digest = _token_hash(token)
        if not hmac.compare_digest(existing.token_hash, digest):
            raise ProjectHandoffError("project handoff signing key changed")
        return token

    expires_at = now + timedelta(seconds=HANDOFF_TTL_SECONDS)
    token = _token(project_id, idempotency_key, expires_at)
    digest = _token_hash(token)
    db.add(ProjectHandoffDB(
        id=str(uuid.uuid4()),
        project_id=project_id,
        source_scope_id=source_scope_id,
        token_hash=digest,
        idempotency_key=idempotency_key,
        expires_at=expires_at,
        created_at=now,
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(ProjectHandoffDB).filter(
            ProjectHandoffDB.idempotency_key == idempotency_key,
        ).first()
        if existing is not None:
            token = _token(project_id, idempotency_key, existing.expires_at)
            digest = _token_hash(token)
        if (
            existing is None
            or existing.project_id != project_id
            or existing.source_scope_id != source_scope_id
            or not hmac.compare_digest(existing.token_hash, digest)
        ):
            raise ProjectHandoffError("project handoff idempotency conflict")
    return token


def claim_project_handoff(
    db: Session,
    *,
    project_id: str,
    target_scope_id: str,
    token: str,
) -> dict:
    """Grant one signed browser scope access to the Telegram project."""

    if len(token) != 43 or not all(character.isalnum() or character in "-_" for character in token):
        raise ProjectHandoffNotFound(project_id)
    digest = _token_hash(token)
    _handoff_signing_key()
    now = _now()
    handoff = db.query(ProjectHandoffDB).filter(
        ProjectHandoffDB.project_id == project_id,
        ProjectHandoffDB.token_hash == digest,
    ).first()
    if handoff is None:
        raise ProjectHandoffNotFound(project_id)

    project = db.query(ProjectDB).filter(
        ProjectDB.id == project_id,
        ProjectDB.scope_id == handoff.source_scope_id,
        ProjectDB.deleted_at.is_(None),
    ).first()
    if project is None:
        raise ProjectHandoffNotFound(project_id)
    access = None
    if target_scope_id != project.scope_id:
        access = db.query(ProjectAccessDB).filter(
            ProjectAccessDB.project_id == project_id,
            ProjectAccessDB.scope_id == target_scope_id,
        ).first()

    if handoff.claimed_by_scope_id is not None:
        authorized_target = (
            target_scope_id == project.scope_id
            or (access is not None and access.revoked_at is None)
        )
        if not authorized_target:
            raise ProjectHandoffAlreadyClaimed(project_id)
        return project_to_dict(project)
    if _utc(handoff.expires_at) <= now:
        raise ProjectHandoffExpired(project_id)

    claimed = db.query(ProjectHandoffDB).filter(
        ProjectHandoffDB.id == handoff.id,
        ProjectHandoffDB.expires_at > now,
        (
            ProjectHandoffDB.claimed_by_scope_id.is_(None)
            | (ProjectHandoffDB.claimed_by_scope_id == target_scope_id)
        ),
    ).update(
        {
            ProjectHandoffDB.claimed_by_scope_id: target_scope_id,
            ProjectHandoffDB.claimed_at: handoff.claimed_at or now,
        },
        synchronize_session=False,
    )
    if claimed != 1:
        db.rollback()
        current = db.query(ProjectHandoffDB).filter(
            ProjectHandoffDB.project_id == project_id,
            ProjectHandoffDB.token_hash == digest,
        ).first()
        if current is not None and _utc(current.expires_at) <= now:
            raise ProjectHandoffExpired(project_id)
        raise ProjectHandoffAlreadyClaimed(project_id)

    if target_scope_id != project.scope_id:
        if access is None:
            db.add(ProjectAccessDB(
                id=str(uuid.uuid4()),
                project_id=project_id,
                scope_id=target_scope_id,
                permission="read_write",
                source="telegram_handoff",
                created_at=now,
            ))
        else:
            access.permission = "read_write"
            access.source = "telegram_handoff"
            access.revoked_at = None

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        handoff = db.query(ProjectHandoffDB).filter(
            ProjectHandoffDB.project_id == project_id,
            ProjectHandoffDB.token_hash == digest,
        ).first()
        if handoff is None or handoff.claimed_by_scope_id != target_scope_id:
            raise ProjectHandoffAlreadyClaimed(project_id)
    return project_to_dict(project)


def adopt_anonymous_project_access(
    db: Session,
    *,
    anonymous_cookie: str | None,
    target_scope_id: str,
) -> int:
    """Move active handoff grants from a signed guest session to its user."""

    anonymous = validate_anonymous_session(anonymous_cookie)
    if anonymous is None or anonymous.scope_id == target_scope_id:
        return 0

    now = _now()
    grants = db.query(ProjectAccessDB).filter(
        ProjectAccessDB.scope_id == anonymous.scope_id,
        ProjectAccessDB.permission == "read_write",
        ProjectAccessDB.revoked_at.is_(None),
    ).with_for_update().all()
    adopted = 0
    for grant in grants:
        project = db.query(ProjectDB).filter(
            ProjectDB.id == grant.project_id,
            ProjectDB.deleted_at.is_(None),
        ).first()
        if project is None:
            continue
        if project.scope_id != target_scope_id:
            target = db.query(ProjectAccessDB).filter(
                ProjectAccessDB.project_id == grant.project_id,
                ProjectAccessDB.scope_id == target_scope_id,
            ).first()
            if target is None:
                db.add(ProjectAccessDB(
                    id=str(uuid.uuid4()),
                    project_id=grant.project_id,
                    scope_id=target_scope_id,
                    permission="read_write",
                    source="browser_account_adoption",
                    created_at=now,
                ))
            else:
                target.permission = "read_write"
                target.source = "browser_account_adoption"
                target.revoked_at = None
        # Account adoption is a terminal transfer, not a surface-level unlink
        # that the old anonymous principal may undo through Project restore.
        db.delete(grant)
        adopted += 1
    db.flush()
    return adopted


def _contains_cas_reference(value) -> bool:
    if isinstance(value, dict):
        if str(value.get("type") or "") in {"present_artifact", "present_image"}:
            return True
        for key, nested in value.items():
            if key in {"artifact", "artifact_id", "artifact_ids"} and nested:
                return True
            if _contains_cas_reference(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_cas_reference(item) for item in value)
    return False


def adopt_anonymous_roots(
    db: Session,
    *,
    anonymous_cookie: str | None,
    target_scope_id: str,
    target_organization_id: str,
    actor_user_id: str,
) -> dict[str, int]:
    """Atomically transfer supported anonymous roots into one organization.

    CAS manifests bind immutable bytes to their original scope.  Until a
    verified manifest rewrite exists, any detected CAS reference aborts the
    whole transfer instead of producing a project whose attachments return
    cross-scope authorization failures.
    """

    anonymous = validate_anonymous_session(anonymous_cookie)
    if anonymous is None or anonymous.scope_id == target_scope_id:
        return {"projects": 0, "estimates": 0, "documents": 0, "responses": 0}

    source_scope_id = anonymous.scope_id
    projects = db.query(ProjectDB).filter(
        ProjectDB.scope_id == source_scope_id,
    ).with_for_update().all()
    project_ids = [project.id for project in projects]
    if project_ids:
        message_metadata = db.query(ProjectMessageDB.attributes).filter(
            ProjectMessageDB.project_id.in_(project_ids)
        ).all()
        if any(_contains_cas_reference(attributes) for (attributes,) in message_metadata):
            raise AnonymousAdoptionUnsupported("anonymous_cas_adoption_unsupported")

    responses = db.query(PublicResponseDB).filter(
        PublicResponseDB.owner_scope == source_scope_id,
    ).with_for_update().all()
    if any(
        response.status not in {"completed", "failed", "cancelled"}
        for response in responses
    ):
        raise AnonymousAdoptionUnsupported("anonymous_response_adoption_in_progress")
    if any(_contains_cas_reference(response.payload or {}) for response in responses):
        raise AnonymousAdoptionUnsupported("anonymous_cas_adoption_unsupported")

    counts = {
        "projects": len(projects),
        "estimates": db.query(EstimateDB).filter(
            EstimateDB.scope_id == source_scope_id
        ).count(),
        "documents": db.query(DocumentDB).filter(
            DocumentDB.scope_id == source_scope_id
        ).count(),
        "responses": len(responses),
    }
    for project in projects:
        project.scope_id = target_scope_id
        project.organization_id = target_organization_id
    if project_ids:
        db.query(ProjectMessageDB).filter(
            ProjectMessageDB.project_id.in_(project_ids)
        ).update(
            {ProjectMessageDB.scope_id: target_scope_id},
            synchronize_session=False,
        )
        message_ids = select(ProjectMessageDB.id).where(
            ProjectMessageDB.project_id.in_(project_ids)
        )
        db.query(ProjectMessageMutationDB).filter(
            ProjectMessageMutationDB.message_id.in_(message_ids)
        ).update(
            {ProjectMessageMutationDB.scope_id: target_scope_id},
            synchronize_session=False,
        )
        # Previously issued anonymous handoffs must not outlive the ownership
        # transfer and grant a stale bearer path into the organization.
        db.query(ProjectHandoffDB).filter(
            ProjectHandoffDB.project_id.in_(project_ids)
        ).delete(synchronize_session=False)

    db.query(EstimateDB).filter(EstimateDB.scope_id == source_scope_id).update(
        {
            EstimateDB.scope_id: target_scope_id,
            EstimateDB.organization_id: target_organization_id,
        },
        synchronize_session=False,
    )
    db.query(DocumentDB).filter(DocumentDB.scope_id == source_scope_id).update(
        {
            DocumentDB.scope_id: target_scope_id,
            DocumentDB.organization_id: target_organization_id,
        },
        synchronize_session=False,
    )
    db.query(PublicResponseDB).filter(
        PublicResponseDB.owner_scope == source_scope_id
    ).update(
        {
            PublicResponseDB.owner_scope: target_scope_id,
            PublicResponseDB.organization_id: target_organization_id,
        },
        synchronize_session=False,
    )
    if any(counts.values()):
        db.add(
            OrganizationAuditEventDB(
                id=str(uuid.uuid4()),
                organization_id=target_organization_id,
                actor_user_id=actor_user_id,
                action="organization.anonymous_roots_adopted",
                target_type="organization",
                target_id=target_organization_id,
                attributes={
                    "source_scope_hash": hashlib.sha256(
                        source_scope_id.encode("utf-8")
                    ).hexdigest(),
                    "counts": json.loads(json.dumps(counts)),
                },
                created_at=_now(),
            )
        )
    db.flush()
    return counts
