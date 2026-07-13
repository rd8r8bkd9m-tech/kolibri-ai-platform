"""Server-backed project and conversation history API."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.browser_session import ProjectPrincipal, resolve_project_principal
from app.database import get_db
from app.project_history import (
    MessageNotFoundError,
    ProjectConflictError,
    ProjectHistoryRepository,
    ProjectNotFoundError,
    ProjectTransitionError,
)
from app.project_schemas import (
    ProjectCreate,
    ProjectListResponse,
    ProjectMessageCreate,
    ProjectMessageListResponse,
    ProjectMessageResponse,
    ProjectMessageUpdate,
    ProjectResponse,
    ProjectUpdate,
)


router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def _message_payload(data: ProjectMessageCreate | ProjectMessageUpdate, *, exclude_unset: bool = False) -> dict:
    payload = data.model_dump(exclude_unset=exclude_unset)
    if "metadata" in payload and data.metadata is not None:
        payload["metadata"] = data.metadata.model_dump(exclude_none=True, exclude_defaults=True)
    return payload


def _idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    key = value.strip()
    if not key or len(key) > 128:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_idempotency_key", "message": "Idempotency-Key must contain 1..128 characters"},
        )
    return key


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "project_not_found", "message": "Project not found"},
    )


def _conflict(exc: ProjectConflictError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": "idempotency_conflict", "message": str(exc)},
    )


def _message_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "message_not_found", "message": "Project message not found"},
    )


def _transition_conflict(exc: ProjectTransitionError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": "invalid_message_transition", "message": str(exc)},
    )


@router.get("", response_model=ProjectListResponse)
def list_projects(
    include_deleted: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    result = ProjectHistoryRepository(db, principal.scope_id).list_projects(
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
    )
    return {**result, "page": page, "page_size": page_size}


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(
    data: ProjectCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    try:
        result, created = ProjectHistoryRepository(db, principal.scope_id).create_project(
            data.model_dump(),
            _idempotency_key(idempotency_key),
        )
    except ProjectConflictError as exc:
        raise _conflict(exc) from exc
    response.status_code = 201 if created else 200
    return result


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    try:
        return ProjectHistoryRepository(db, principal.scope_id).get_project(project_id)
    except ProjectNotFoundError as exc:
        raise _not_found() from exc


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    data: ProjectUpdate,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    try:
        return ProjectHistoryRepository(db, principal.scope_id).update_project(
            project_id,
            data.model_dump(exclude_unset=True),
        )
    except ProjectNotFoundError as exc:
        raise _not_found() from exc


@router.delete("/{project_id}", response_model=ProjectResponse)
def delete_project(
    project_id: str,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    try:
        return ProjectHistoryRepository(db, principal.scope_id).soft_delete_project(project_id)
    except ProjectNotFoundError as exc:
        raise _not_found() from exc


@router.post("/{project_id}/restore", response_model=ProjectResponse)
def restore_project(
    project_id: str,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    try:
        return ProjectHistoryRepository(db, principal.scope_id).restore_project(project_id)
    except ProjectNotFoundError as exc:
        raise _not_found() from exc


@router.get("/{project_id}/messages", response_model=ProjectMessageListResponse)
def list_project_messages(
    project_id: str,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    try:
        result = ProjectHistoryRepository(db, principal.scope_id).list_messages(
            project_id,
            after=after,
            limit=limit,
        )
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    return {**result, "after": after, "limit": limit}


@router.post("/{project_id}/messages", response_model=ProjectMessageResponse, status_code=201)
def append_project_message(
    project_id: str,
    data: ProjectMessageCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    try:
        result, created = ProjectHistoryRepository(db, principal.scope_id).append_message(
            project_id,
            _message_payload(data),
            _idempotency_key(idempotency_key),
        )
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    except ProjectConflictError as exc:
        raise _conflict(exc) from exc
    response.status_code = 201 if created else 200
    return result


@router.patch("/{project_id}/messages/{message_id}", response_model=ProjectMessageResponse)
def update_project_message(
    project_id: str,
    message_id: str,
    data: ProjectMessageUpdate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    try:
        result, _ = ProjectHistoryRepository(db, principal.scope_id).update_message(
            project_id,
            message_id,
            _message_payload(data, exclude_unset=True),
            _idempotency_key(idempotency_key),
        )
        return result
    except ProjectNotFoundError as exc:
        raise _not_found() from exc
    except MessageNotFoundError as exc:
        raise _message_not_found() from exc
    except ProjectConflictError as exc:
        raise _conflict(exc) from exc
    except ProjectTransitionError as exc:
        raise _transition_conflict(exc) from exc
