"""Durable project/thread repository.

SQLite is supported as a bootstrap store. The repository keeps tenancy,
idempotency and sequencing explicit so the same contract can move to
PostgreSQL without changing callers.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ProjectAccessDB, ProjectDB, ProjectMessageDB, ProjectMessageMutationDB


DEFAULT_PROJECT_TITLE = "Новый проект"
MAX_DERIVED_TITLE_LENGTH = 72


class ProjectNotFoundError(Exception):
    pass


class ProjectConflictError(Exception):
    pass


class MessageNotFoundError(Exception):
    pass


class ProjectTransitionError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def derive_project_title(content: str) -> str:
    """Build a stable human title from the first user message."""

    value = re.sub(r"```(?:\w+)?", " ", content)
    value = re.sub(r"[`*_#>]", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" \t\r\n-–—:;,.!?…")
    if not value:
        return DEFAULT_PROJECT_TITLE
    if len(value) <= MAX_DERIVED_TITLE_LENGTH:
        return value
    candidate = value[: MAX_DERIVED_TITLE_LENGTH - 1].rstrip()
    if " " in candidate:
        candidate = candidate.rsplit(" ", 1)[0]
    return f"{candidate.rstrip(' ,.;:!?')}…"


def project_to_dict(project: ProjectDB) -> dict[str, Any]:
    return {
        "id": project.id,
        "title": project.title,
        "title_source": project.title_source,
        "status": project.status,
        "version": project.version,
        "message_count": project.message_count,
        "metadata": dict(project.attributes or {}),
        "created_at": _utc(project.created_at),
        "updated_at": _utc(project.updated_at),
        "last_message_at": _utc(project.last_message_at),
        "deleted_at": _utc(project.deleted_at),
    }


def message_to_dict(message: ProjectMessageDB) -> dict[str, Any]:
    return {
        "id": message.id,
        "project_id": message.project_id,
        "sequence": message.sequence,
        "version": message.version,
        "role": message.role,
        "content": message.content,
        "status": message.status,
        "metadata": dict(message.attributes or {}),
        "created_at": _utc(message.created_at),
        "updated_at": _utc(message.updated_at),
    }


def _message_snapshot(message: ProjectMessageDB) -> dict[str, Any]:
    payload = message_to_dict(message)
    payload["created_at"] = payload["created_at"].isoformat()
    payload["updated_at"] = payload["updated_at"].isoformat()
    return payload


class ProjectHistoryRepository:
    def __init__(
        self,
        db: Session,
        scope_id: str,
        organization_id: str | None = None,
    ):
        self.db = db
        self.scope_id = scope_id
        self.organization_id = organization_id

    def _project_query(self, *, include_deleted: bool = False):
        granted = self.db.query(ProjectAccessDB.id).filter(
            ProjectAccessDB.project_id == ProjectDB.id,
            ProjectAccessDB.scope_id == self.scope_id,
            ProjectAccessDB.permission == "read_write",
            ProjectAccessDB.revoked_at.is_(None),
        ).exists()
        query = self.db.query(ProjectDB).filter(
            or_(ProjectDB.scope_id == self.scope_id, granted)
        )
        if not include_deleted:
            query = query.filter(ProjectDB.deleted_at.is_(None))
        return query

    def _get_project_row(self, project_id: str, *, include_deleted: bool = False, lock: bool = False) -> ProjectDB:
        query = self._project_query(include_deleted=include_deleted).filter(ProjectDB.id == project_id)
        if lock:
            query = query.with_for_update()
        project = query.first()
        if project is None:
            raise ProjectNotFoundError(project_id)
        return project

    def list_projects(self, *, include_deleted: bool, page: int, page_size: int) -> dict[str, Any]:
        query = self._project_query(include_deleted=include_deleted)
        total = query.count()
        activity_at = func.coalesce(ProjectDB.last_message_at, ProjectDB.updated_at, ProjectDB.created_at)
        projects = (
            query.order_by(activity_at.desc(), ProjectDB.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {"items": [project_to_dict(item) for item in projects], "total": total}

    def create_project(self, data: dict[str, Any], idempotency_key: str | None) -> tuple[dict[str, Any], bool]:
        key = idempotency_key or data.get("client_request_id")
        title = data.get("title") or DEFAULT_PROJECT_TITLE
        title_source = "manual" if data.get("title") else "default"
        payload = {"title": title, "metadata": data.get("metadata") or {}}
        fingerprint = _request_hash(payload)

        if key:
            existing = self.db.query(ProjectDB).filter(
                ProjectDB.scope_id == self.scope_id,
                ProjectDB.idempotency_key == key,
            ).first()
            if existing is not None:
                if existing.create_request_hash != fingerprint:
                    raise ProjectConflictError("idempotency key was already used with another project payload")
                return project_to_dict(existing), False

        now = _now()
        project = ProjectDB(
            id=_uid(),
            scope_id=self.scope_id,
            organization_id=self.organization_id,
            title=title,
            title_source=title_source,
            attributes=data.get("metadata") or {},
            idempotency_key=key,
            create_request_hash=fingerprint,
            created_at=now,
            updated_at=now,
        )
        self.db.add(project)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            if not key:
                raise
            existing = self.db.query(ProjectDB).filter(
                ProjectDB.scope_id == self.scope_id,
                ProjectDB.idempotency_key == key,
            ).first()
            if existing is None or existing.create_request_hash != fingerprint:
                raise ProjectConflictError("idempotency key conflict")
            return project_to_dict(existing), False
        self.db.refresh(project)
        return project_to_dict(project), True

    def get_project(self, project_id: str, *, include_deleted: bool = False) -> dict[str, Any]:
        return project_to_dict(self._get_project_row(project_id, include_deleted=include_deleted))

    def update_project(self, project_id: str, data: dict[str, Any]) -> dict[str, Any]:
        project = self._get_project_row(project_id, lock=True)
        if data.get("title") is not None:
            project.title = data["title"]
            project.title_source = "manual"
        if data.get("metadata") is not None:
            project.attributes = data["metadata"]
        project.version += 1
        project.updated_at = _now()
        self.db.commit()
        self.db.refresh(project)
        return project_to_dict(project)

    def soft_delete_project(self, project_id: str) -> dict[str, Any]:
        project = self._get_project_row(project_id, lock=True)
        now = _now()
        if project.scope_id != self.scope_id:
            access = self.db.query(ProjectAccessDB).filter(
                ProjectAccessDB.project_id == project_id,
                ProjectAccessDB.scope_id == self.scope_id,
                ProjectAccessDB.permission == "read_write",
                ProjectAccessDB.revoked_at.is_(None),
            ).with_for_update().first()
            if access is None:
                raise ProjectNotFoundError(project_id)
            access.revoked_at = now
            self.db.commit()
            result = project_to_dict(project)
            result["status"] = "deleted"
            result["deleted_at"] = now
            result["updated_at"] = now
            return result
        project.deleted_at = now
        project.status = "deleted"
        project.version += 1
        project.updated_at = now
        self.db.commit()
        self.db.refresh(project)
        return project_to_dict(project)

    def restore_project(self, project_id: str) -> dict[str, Any]:
        owned = self.db.query(ProjectDB).filter(
            ProjectDB.id == project_id,
            ProjectDB.scope_id == self.scope_id,
        ).with_for_update().first()
        if owned is None:
            access = self.db.query(ProjectAccessDB).filter(
                ProjectAccessDB.project_id == project_id,
                ProjectAccessDB.scope_id == self.scope_id,
                ProjectAccessDB.permission == "read_write",
            ).with_for_update().first()
            project = self.db.query(ProjectDB).filter(
                ProjectDB.id == project_id,
                ProjectDB.deleted_at.is_(None),
            ).with_for_update().first()
            if access is None or project is None:
                raise ProjectNotFoundError(project_id)
            if access.revoked_at is not None:
                access.revoked_at = None
                self.db.commit()
            return project_to_dict(project)

        project = owned
        if project.deleted_at is None:
            return project_to_dict(project)
        project.deleted_at = None
        project.status = "active"
        project.version += 1
        project.updated_at = _now()
        self.db.commit()
        self.db.refresh(project)
        return project_to_dict(project)

    def list_messages(self, project_id: str, *, after: int, limit: int) -> dict[str, Any]:
        self._get_project_row(project_id)
        query = self.db.query(ProjectMessageDB).filter(
            ProjectMessageDB.project_id == project_id,
        )
        total = query.count()
        messages = (
            query.filter(ProjectMessageDB.sequence > after)
            .order_by(ProjectMessageDB.sequence.asc())
            .limit(limit)
            .all()
        )
        return {"items": [message_to_dict(item) for item in messages], "total": total}

    def _get_message_row(self, project_id: str, message_id: str, *, lock: bool = False) -> ProjectMessageDB:
        self._get_project_row(project_id)
        query = self.db.query(ProjectMessageDB).filter(
            ProjectMessageDB.id == message_id,
            ProjectMessageDB.project_id == project_id,
        )
        if lock:
            query = query.with_for_update()
        message = query.first()
        if message is None:
            raise MessageNotFoundError(message_id)
        return message

    def append_message(
        self,
        project_id: str,
        data: dict[str, Any],
        idempotency_key: str | None,
    ) -> tuple[dict[str, Any], bool]:
        key = idempotency_key or data.get("client_message_id")
        payload = {
            "role": data["role"],
            "content": data["content"],
            "status": data.get("status", "completed"),
            "metadata": data.get("metadata") or {},
        }
        fingerprint = _request_hash(payload)

        project = self._get_project_row(project_id, lock=True)
        if key:
            existing = self.db.query(ProjectMessageDB).filter(
                ProjectMessageDB.project_id == project_id,
                ProjectMessageDB.idempotency_key == key,
            ).first()
            if existing is not None:
                if existing.request_hash != fingerprint:
                    raise ProjectConflictError("idempotency key was already used with another message payload")
                return message_to_dict(existing), False

        first_user_message = data["role"] == "user" and not self.db.query(ProjectMessageDB.id).filter(
            ProjectMessageDB.project_id == project_id,
            ProjectMessageDB.role == "user",
        ).first()
        now = _now()
        message = ProjectMessageDB(
            id=_uid(),
            project_id=project_id,
            scope_id=self.scope_id,
            sequence=project.message_count + 1,
            version=1,
            role=data["role"],
            content=data["content"],
            status=data.get("status", "completed"),
            attributes=data.get("metadata") or {},
            idempotency_key=key,
            request_hash=fingerprint,
            created_at=now,
            updated_at=now,
        )
        self.db.add(message)
        project.message_count += 1
        project.last_message_at = now
        project.updated_at = now
        project.version += 1
        if first_user_message and project.title_source == "default":
            project.title = derive_project_title(data["content"])
            project.title_source = "message"
        if first_user_message:
            from app.project_case import ensure_case_for_first_message

            ensure_case_for_first_message(
                project,
                source_message_id=message.id,
                prompt=data["content"],
            )
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            if not key:
                raise
            existing = self.db.query(ProjectMessageDB).filter(
                ProjectMessageDB.project_id == project_id,
                ProjectMessageDB.idempotency_key == key,
            ).first()
            if existing is None or existing.request_hash != fingerprint:
                raise ProjectConflictError("idempotency key conflict")
            return message_to_dict(existing), False
        self.db.refresh(message)
        return message_to_dict(message), True

    def update_message(
        self,
        project_id: str,
        message_id: str,
        data: dict[str, Any],
        idempotency_key: str | None,
    ) -> tuple[dict[str, Any], bool]:
        payload = {
            key: value
            for key, value in {
                "content": data.get("content"),
                "status": data.get("status"),
                "metadata": data.get("metadata"),
            }.items()
            if value is not None
        }
        fingerprint = _request_hash(payload)
        message = self._get_message_row(project_id, message_id, lock=True)

        if message.role != "assistant":
            raise ProjectTransitionError("only assistant placeholders have a mutable lifecycle")

        if idempotency_key:
            existing_mutation = self.db.query(ProjectMessageMutationDB).filter(
                ProjectMessageMutationDB.message_id == message_id,
                ProjectMessageMutationDB.idempotency_key == idempotency_key,
                ProjectMessageMutationDB.scope_id == self.scope_id,
            ).first()
            if existing_mutation is not None:
                if existing_mutation.request_hash != fingerprint:
                    raise ProjectConflictError("idempotency key was already used with another message update")
                return dict(existing_mutation.response_payload), False

        current_status = message.status
        target_status = data.get("status") or current_status
        allowed_transitions = {
            "pending": {"pending", "streaming", "completed", "failed", "cancelled"},
            "streaming": {"streaming", "completed", "failed", "cancelled"},
            "completed": {"completed"},
            "failed": {"failed"},
            "cancelled": {"cancelled"},
        }
        if target_status not in allowed_transitions.get(current_status, set()):
            raise ProjectTransitionError(f"message cannot move from {current_status} to {target_status}")

        target_content = data["content"] if data.get("content") is not None else message.content
        target_metadata = data["metadata"] if data.get("metadata") is not None else dict(message.attributes or {})
        if target_status == "completed" and not target_content.strip():
            raise ProjectTransitionError("a completed assistant message must contain content")

        unchanged = (
            target_status == message.status
            and target_content == message.content
            and target_metadata == dict(message.attributes or {})
        )
        if unchanged:
            return message_to_dict(message), False

        project = self._get_project_row(project_id, lock=True)
        now = _now()
        message.content = target_content
        message.status = target_status
        message.attributes = target_metadata
        message.version += 1
        message.updated_at = now
        project.updated_at = now
        project.last_message_at = now
        project.version += 1
        self.db.flush()

        if idempotency_key:
            mutation = ProjectMessageMutationDB(
                id=_uid(),
                message_id=message.id,
                scope_id=self.scope_id,
                idempotency_key=idempotency_key,
                request_hash=fingerprint,
                response_payload=_message_snapshot(message),
                created_at=now,
            )
            self.db.add(mutation)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            if not idempotency_key:
                raise
            existing_mutation = self.db.query(ProjectMessageMutationDB).filter(
                ProjectMessageMutationDB.message_id == message_id,
                ProjectMessageMutationDB.idempotency_key == idempotency_key,
                ProjectMessageMutationDB.scope_id == self.scope_id,
            ).first()
            if existing_mutation is None or existing_mutation.request_hash != fingerprint:
                raise ProjectConflictError("idempotency key conflict")
            return dict(existing_mutation.response_payload), False
        self.db.refresh(message)
        return message_to_dict(message), True
