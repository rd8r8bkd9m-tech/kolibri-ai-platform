"""Server-backed project and conversation history API."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.browser_session import ProjectPrincipal, resolve_project_principal
from app.artifact_store import (
    ArtifactStoreError,
    _assert_http_artifact_access,
    get_artifact_store,
)
from app.database import get_db
from app.project_history import (
    MessageNotFoundError,
    ProjectConflictError,
    ProjectHistoryRepository,
    ProjectNotFoundError,
    ProjectTransitionError,
)
from app.project_handoff import (
    ProjectHandoffAlreadyClaimed,
    ProjectHandoffConfigurationError,
    ProjectHandoffExpired,
    ProjectHandoffNotFound,
    claim_project_handoff,
)
from app.project_schemas import (
    ProjectCreate,
    ProjectHandoffClaim,
    ProjectListResponse,
    ProjectMessageCreate,
    PersistedFileAction,
    PersistedFileArtifact,
    PersistedFileArtifactReference,
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


def _persisted_file_artifacts(
    data: ProjectMessageCreate | ProjectMessageUpdate,
) -> list[PersistedFileArtifact]:
    metadata = data.metadata
    if metadata is None:
        return []
    artifacts: list[PersistedFileArtifact] = []
    if isinstance(metadata.artifact, PersistedFileArtifactReference):
        artifacts.append(metadata.artifact.value)
    artifacts.extend(
        action.data
        for action in metadata.actions
        if isinstance(action, PersistedFileAction)
    )
    return artifacts


def _verify_persisted_file_artifacts(
    data: ProjectMessageCreate | ProjectMessageUpdate,
    principal: ProjectPrincipal,
) -> None:
    """Bind browser-persisted file metadata to real scoped CAS bytes."""

    artifacts = _persisted_file_artifacts(data)
    if not artifacts:
        return
    store = get_artifact_store()
    try:
        for artifact in artifacts:
            stored = store.open(artifact.id, revision=artifact.revision)
            _assert_http_artifact_access(stored.manifest, principal)
            submitted = artifact.model_dump(exclude_none=True)
            canonical = {
                key: stored.manifest.get(key)
                for key in submitted
            }
            if canonical != submitted or not stored.content:
                raise ValueError("artifact_manifest_mismatch")
    except (ArtifactStoreError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "artifact_manifest_unverified",
                "message": "Artifact metadata is not bound to scoped CAS bytes",
            },
        ) from exc


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
    result = ProjectHistoryRepository(
        db, principal.scope_id, principal.organization_id
    ).list_projects(
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
    )
    from app.capability_runtime import record_capability_invocation

    record_capability_invocation(
        "project.history",
        succeeded=True,
        provider="postgres-project-history",
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
        result, created = ProjectHistoryRepository(
            db, principal.scope_id, principal.organization_id
        ).create_project(
            data.model_dump(),
            _idempotency_key(idempotency_key),
        )
    except ProjectConflictError as exc:
        raise _conflict(exc) from exc
    from app.capability_runtime import record_capability_invocation

    record_capability_invocation(
        "project.history",
        succeeded=True,
        provider="postgres-project-history",
        evidence_id=str(result.get("id") or ""),
    )
    response.status_code = 201 if created else 200
    return result


@router.post("/{project_id}/claim", response_model=ProjectResponse)
def claim_project(
    project_id: str,
    data: ProjectHandoffClaim,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    try:
        return claim_project_handoff(
            db,
            project_id=project_id,
            target_scope_id=principal.scope_id,
            token=data.token,
        )
    except ProjectHandoffNotFound as exc:
        raise _not_found() from exc
    except ProjectHandoffConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "project_handoff_unavailable", "message": "Project handoff is unavailable"},
        ) from exc
    except ProjectHandoffExpired as exc:
        raise HTTPException(
            status_code=410,
            detail={"code": "project_handoff_expired", "message": "Project handoff expired"},
        ) from exc
    except ProjectHandoffAlreadyClaimed as exc:
        raise HTTPException(
            status_code=410,
            detail={"code": "project_handoff_already_claimed", "message": "Project handoff was already claimed"},
        ) from exc


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    try:
        return ProjectHistoryRepository(
            db, principal.scope_id, principal.organization_id
        ).get_project(project_id)
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
        return ProjectHistoryRepository(
            db, principal.scope_id, principal.organization_id
        ).update_project(
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
        return ProjectHistoryRepository(
            db, principal.scope_id, principal.organization_id
        ).soft_delete_project(project_id)
    except ProjectNotFoundError as exc:
        raise _not_found() from exc


@router.post("/{project_id}/restore", response_model=ProjectResponse)
def restore_project(
    project_id: str,
    principal: ProjectPrincipal = Depends(resolve_project_principal),
    db: Session = Depends(get_db),
):
    try:
        return ProjectHistoryRepository(
            db, principal.scope_id, principal.organization_id
        ).restore_project(project_id)
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
        result = ProjectHistoryRepository(
            db, principal.scope_id, principal.organization_id
        ).list_messages(
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
    _verify_persisted_file_artifacts(data, principal)
    try:
        result, created = ProjectHistoryRepository(
            db, principal.scope_id, principal.organization_id
        ).append_message(
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
    _verify_persisted_file_artifacts(data, principal)
    try:
        result, _ = ProjectHistoryRepository(
            db, principal.scope_id, principal.organization_id
        ).update_message(
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
