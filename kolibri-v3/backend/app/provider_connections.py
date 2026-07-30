"""Tenant-scoped Product/Data metadata for provider connections.

Production uses secretless enrollment intents and a standalone authority
worker. The loopback development runtime additionally exposes an owner-only,
CSRF-protected MiMo binding that immediately hands the key to the local
Provider Authority adapter. Credentials are never written to Product tables,
responses or logs.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi import status as http_status

from .agent_runtime import AgentRuntimeRegistry
from .chat.service import (
    canonical_command_hash,
    canonical_json,
    sha256_text,
    typed_identity_id,
)
from .config import Settings
from .database import get_database, transaction
from .identity import require_owner
from .local_provider_authority import (
    LocalProviderAuthorityError,
    install_mimo_key,
    verify_codex_login,
)
from .schemas import UserSession
from .security import require_mutation_auth


router = APIRouter(prefix="/v1/provider-connections", tags=["providers"])

DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
OwnerDependency = Annotated[UserSession, Depends(require_owner)]
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]

# These IDs name the two transport-specific enrollment adapters implemented in
# this module. Common storage and projection accept any registered bounded
# runtime profile; adding a runtime does not add another orchestration branch.
PROVIDER_IDS = ("mimo-code", "codex-cli")
PROVIDER_ENROLLMENT_CAPABILITY = "product.provider.enrollment.request"
_PROVIDER_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,95}$")
_IDEMPOTENCY_NONCE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-"
    r"[0-9a-f]{12}$",
    re.IGNORECASE,
)
_MAX_EMPTY_BODY_BYTES = 2_048
_MAX_CREDENTIAL_BODY_BYTES = 12 * 1_024

_ADAPTER_PROVIDER_NAMES = {
    "mimo-code": "MiMo Code",
    "codex-cli": "Codex CLI",
}
_PRESENTATION = {
    "not_configured": (
        "Не подключён",
        "Подключение не подтверждено Provider Execution Authority.",
    ),
    "pending": (
        "Ожидает подтверждения",
        "Kolibri сохранила запрос. Подключение ожидает безопасного подтверждения на Provider Execution Authority.",
    ),
    "connected": (
        "Подключён",
        "Provider Execution Authority подтвердил работоспособность подключения.",
    ),
    "error": (
        "Требует внимания",
        "Подключение не подтверждено. Секретные сведения остаются скрыты.",
    ),
}


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    id: str
    display_name: str
    enrollment_supported: bool


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "strict")).hexdigest()


def _provider_descriptors(request: Request) -> tuple[ProviderDescriptor, ...]:
    descriptors: dict[str, ProviderDescriptor] = {
        provider_id: ProviderDescriptor(
            id=provider_id,
            display_name=display_name,
            enrollment_supported=True,
        )
        for provider_id, display_name in _ADAPTER_PROVIDER_NAMES.items()
    }
    registry = getattr(
        getattr(request.app, "state", None),
        "agent_runtime_registry",
        None,
    )
    if isinstance(registry, AgentRuntimeRegistry):
        for runtime in registry.descriptors():
            descriptors[runtime.profile_id] = ProviderDescriptor(
                id=runtime.profile_id,
                display_name=runtime.display_name,
                enrollment_supported=runtime.profile_id in PROVIDER_IDS,
            )
    return tuple(
        sorted(
            descriptors.values(),
            key=lambda descriptor: (
                descriptor.id not in PROVIDER_IDS,
                descriptor.display_name.casefold(),
                descriptor.id,
            ),
        )
    )


def _provider_projection(
    row: sqlite3.Row | None,
    descriptor: ProviderDescriptor,
) -> dict[str, Any]:
    connection_status = (
        str(row["status"]) if row is not None else "not_configured"
    )
    status_label, detail = _PRESENTATION[connection_status]
    return {
        "id": descriptor.id,
        "displayName": descriptor.display_name,
        "authMode": "provider_authority",
        "status": connection_status,
        "enrollmentSupported": descriptor.enrollment_supported,
        "authFlowSupported": (
            bool(row["auth_flow_supported"]) if row is not None else False
        ),
        "statusLabel": status_label,
        "detail": detail,
        "lastVerifiedAt": (
            str(row["last_verified_at"])
            if row is not None and row["last_verified_at"] is not None
            else None
        ),
    }


def _connection_rows(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
) -> dict[str, sqlite3.Row]:
    rows = database.execute(
        """
        SELECT *
        FROM provider_connections
        WHERE tenant_id = ?
        ORDER BY provider_id
        """,
        (tenant_id,),
    ).fetchall()
    return {str(row["provider_id"]): row for row in rows}


def _list_response(
    request: Request,
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    authority_configured: bool,
) -> dict[str, Any]:
    rows = _connection_rows(database, tenant_id=tenant_id)
    descriptors = _provider_descriptors(request)
    return {
        "providers": [
            _provider_projection(rows.get(descriptor.id), descriptor)
            for descriptor in descriptors
        ],
        "authorityConfigured": authority_configured,
    }


def _ensure_connection(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    provider_id: str,
    now: str,
) -> sqlite3.Row:
    database.execute(
        """
        INSERT INTO provider_connections (
            tenant_id, provider_id, status, auth_flow_supported,
            authority_observed, last_verified_at, last_evidence_hash,
            last_intent_id, last_error_code, created_at, updated_at
        ) VALUES (
            ?, ?, 'not_configured', 0, 0, NULL, NULL, NULL, NULL, ?, ?
        )
        ON CONFLICT(tenant_id, provider_id) DO NOTHING
        """,
        (tenant_id, provider_id, now, now),
    )
    row = database.execute(
        """
        SELECT *
        FROM provider_connections
        WHERE tenant_id = ? AND provider_id = ?
        """,
        (tenant_id, provider_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("provider connection row was not created")
    return row


def _save_local_connection(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    provider_id: str,
    last_verified_at: str,
    evidence_hash: str,
) -> dict[str, Any]:
    now = _utc_now()
    with transaction(database, immediate=True):
        _ensure_connection(
            database,
            tenant_id=tenant_id,
            provider_id=provider_id,
            now=now,
        )
        database.execute(
            """
            UPDATE provider_connections
            SET status = 'connected',
                auth_flow_supported = 1,
                authority_observed = 1,
                last_verified_at = ?,
                last_evidence_hash = ?,
                last_error_code = NULL,
                updated_at = ?
            WHERE tenant_id = ? AND provider_id = ?
            """,
            (
                last_verified_at,
                evidence_hash,
                now,
                tenant_id,
                provider_id,
            ),
        )
        row = database.execute(
            """
            SELECT *
            FROM provider_connections
            WHERE tenant_id = ? AND provider_id = ?
            """,
            (tenant_id, provider_id),
        ).fetchone()
    return {
        "provider": _provider_projection(
            row,
            ProviderDescriptor(
                id=provider_id,
                display_name=_ADAPTER_PROVIDER_NAMES[provider_id],
                enrollment_supported=True,
            ),
        )
    }


def _validate_idempotency_nonce(value: str | None) -> str:
    candidate = (value or "").strip()
    if not _IDEMPOTENCY_NONCE.fullmatch(candidate):
        raise _error(
            http_status.HTTP_400_BAD_REQUEST,
            "provider_enrollment_idempotency_required",
            "A valid UUIDv4 Idempotency-Key is required.",
        )
    try:
        parsed = uuid.UUID(candidate)
    except ValueError:
        parsed = None
    if parsed is None or parsed.version != 4 or parsed.variant != uuid.RFC_4122:
        raise _error(
            http_status.HTTP_400_BAD_REQUEST,
            "provider_enrollment_idempotency_required",
            "A valid UUIDv4 Idempotency-Key is required.",
        )
    return str(parsed)


def _build_command(
    *,
    settings: Settings,
    identity: UserSession,
    provider_id: str,
    intent_id: str,
    requested_at: str,
    idempotency_digest: str,
    owner_authorization_decision_id: str,
) -> dict[str, Any]:
    grant = settings.require_product_authority_grant()
    if PROVIDER_ENROLLMENT_CAPABILITY not in grant.capabilities:
        raise _error(
            http_status.HTTP_503_SERVICE_UNAVAILABLE,
            "provider_enrollment_authority_not_configured",
            "Provider enrollment authority is not configured.",
        )

    typed_tenant_id = typed_identity_id("tenant", identity.tenant_id)
    typed_user_id = typed_identity_id("user", identity.user_id)
    actor_id = typed_identity_id("actor", identity.user_id)
    trace_seed = _sha256_hex(f"trace\0{intent_id}")
    deadline_at = (
        datetime.fromisoformat(requested_at)
        + timedelta(seconds=settings.provider_enrollment_command_deadline_seconds)
    ).isoformat()
    payload = {
        "schema_id": "kolibri.product.provider.enrollment_intent.command",
        "schema_version": "1.0",
        "tenant_id": typed_tenant_id,
        "intent_id": intent_id,
        "provider_id": provider_id,
        "requested_by_user_id": typed_user_id,
        "owner_authorization_decision_id": (
            owner_authorization_decision_id
        ),
        "purpose": "owner_provider_enrollment",
        "requested_at": requested_at,
    }
    command: dict[str, Any] = {
        "schema_id": "kolibri.command",
        "schema_version": "1.0",
        "message_id": f"cmd_{idempotency_digest}",
        "command_name": "product.provider.enrollment.request",
        "payload_schema_id": (
            "kolibri.product.provider.enrollment_intent.command"
        ),
        "payload_schema_version": "1.0",
        "issued_at": requested_at,
        "deadline_at": deadline_at,
        "target_owner": "provider_execution_authority",
        "identity": {
            "tenant_id": typed_tenant_id,
            "user_id": typed_user_id,
            "actor": {
                "actor_id": actor_id,
                "actor_type": "user",
            },
            "authority": grant.as_identity_authority(),
            "subject_refs": {
                "goal_id": None,
                "case_id": None,
                "task_id": None,
            },
        },
        "trace": {
            "trace_id": trace_seed[:32],
            "span_id": trace_seed[32:48],
            "parent_span_id": None,
            "correlation_id": intent_id,
            "causation_id": None,
        },
        "idempotency": {
            "key": f"product.provider.enrollment:{intent_id}",
            "scope": "aggregate",
            "scope_id": intent_id,
            "canonical_request_hash": "",
        },
        "payload": payload,
    }
    command["idempotency"]["canonical_request_hash"] = canonical_command_hash(
        command
    )
    return command


@router.get("")
def list_provider_connections(
    request: Request,
    database: DatabaseDependency,
    identity: OwnerDependency,
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    return _list_response(
        request,
        database,
        tenant_id=identity.tenant_id,
        authority_configured=(
            settings.provider_authority_dispatch_configured
        ),
    )


@router.post(
    "/{provider_id}/enrollment-intents",
    status_code=http_status.HTTP_202_ACCEPTED,
)
async def create_provider_enrollment_intent(
    provider_id: str,
    request: Request,
    database: DatabaseDependency,
    identity: OwnerDependency,
    _auth: MutationAuthDependency,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
) -> Response:
    descriptors = {
        descriptor.id: descriptor
        for descriptor in _provider_descriptors(request)
    }
    if not _PROVIDER_ID.fullmatch(provider_id) or provider_id not in descriptors:
        raise _error(
            http_status.HTTP_404_NOT_FOUND,
            "provider_not_found",
            "Provider was not found.",
        )
    if not descriptors[provider_id].enrollment_supported:
        raise _error(
            http_status.HTTP_409_CONFLICT,
            "provider_enrollment_not_supported",
            (
                "This runtime does not advertise a Provider Authority "
                "enrollment adapter."
            ),
        )
    nonce = _validate_idempotency_nonce(idempotency_key)
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        try:
            if int(declared_length) > _MAX_EMPTY_BODY_BYTES:
                raise _error(
                    http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    "provider_enrollment_body_too_large",
                    "Provider enrollment request body is too large.",
                )
        except ValueError:
            raise _error(
                http_status.HTTP_400_BAD_REQUEST,
                "provider_enrollment_body_invalid",
                "Provider enrollment request body must be empty.",
            ) from None
    body = await request.body()
    if len(body) > _MAX_EMPTY_BODY_BYTES:
        raise _error(
            http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "provider_enrollment_body_too_large",
            "Provider enrollment request body is too large.",
        )
    if body.strip():
        raise _error(
            http_status.HTTP_400_BAD_REQUEST,
            "provider_enrollment_body_forbidden",
            "Provider credentials and request payloads are not accepted.",
        )

    settings: Settings = request.app.state.settings
    if (
        not identity.session_id
        or identity.authenticated_at
        < int(datetime.now(timezone.utc).timestamp())
        - settings.provider_enrollment_reauth_seconds
    ):
        raise _error(
            http_status.HTTP_403_FORBIDDEN,
            "provider_enrollment_reauthentication_required",
            "Sign in again before changing provider connections.",
        )
    idempotency_digest = _sha256_hex(
        "\0".join(
            (
                "kolibri-provider-enrollment-v1",
                identity.tenant_id,
                identity.user_id,
                provider_id,
                nonce,
            )
        )
    )
    intent_id = f"intent_{idempotency_digest}"
    owner_authorization_decision_id = (
        "decision_"
        + _sha256_hex(
            "\0".join(
                (
                    "kolibri-provider-owner-decision-v1",
                    identity.tenant_id,
                    identity.user_id,
                    identity.session_id,
                    str(identity.authenticated_at),
                    intent_id,
                )
            )
        )
    )

    with transaction(database, immediate=True):
        replay = database.execute(
            """
            SELECT api_response_json
            FROM provider_enrollment_intents
            WHERE tenant_id = ?
              AND requested_by_user_id = ?
              AND provider_id = ?
              AND idempotency_key_hash = ?
            LIMIT 1
            """,
            (
                identity.tenant_id,
                identity.user_id,
                provider_id,
                idempotency_digest,
            ),
        ).fetchone()
        if replay is not None:
            response_json = str(replay["api_response_json"])
        else:
            now = _utc_now()
            command = _build_command(
                settings=settings,
                identity=identity,
                provider_id=provider_id,
                intent_id=intent_id,
                requested_at=now,
                idempotency_digest=idempotency_digest,
                owner_authorization_decision_id=(
                    owner_authorization_decision_id
                ),
            )
            command_json = canonical_json(command)
            command_hash = sha256_text(command_json)
            request_hash = canonical_command_hash(command)
            connection = _ensure_connection(
                database,
                tenant_id=identity.tenant_id,
                provider_id=provider_id,
                now=now,
            )
            if database.execute(
                """
                SELECT 1
                FROM provider_enrollment_intents
                WHERE tenant_id = ?
                  AND provider_id = ?
                  AND state IN ('queued', 'leased', 'retry')
                LIMIT 1
                """,
                (identity.tenant_id, provider_id),
            ).fetchone():
                raise _error(
                    http_status.HTTP_409_CONFLICT,
                    "provider_enrollment_already_pending",
                    "A provider enrollment request is already pending.",
                )
            if str(connection["status"]) in {"connected", "pending"}:
                raise _error(
                    http_status.HTTP_409_CONFLICT,
                    (
                        "provider_already_connected"
                        if str(connection["status"]) == "connected"
                        else "provider_enrollment_already_pending"
                    ),
                    (
                        "Provider connection is already confirmed."
                        if str(connection["status"]) == "connected"
                        else "A provider enrollment request is already pending."
                    ),
                )

            dispatch_configured = (
                settings.provider_authority_dispatch_configured
            )
            database.execute(
                """
                UPDATE provider_connections
                SET status = ?,
                    last_intent_id = ?,
                    last_error_code = ?,
                    updated_at = ?
                WHERE tenant_id = ? AND provider_id = ?
                """,
                (
                    "pending" if dispatch_configured else "not_configured",
                    intent_id,
                    (
                        None
                        if dispatch_configured
                        else "provider_authority_dispatch_not_configured"
                    ),
                    now,
                    identity.tenant_id,
                    provider_id,
                ),
            )
            pending_row = database.execute(
                """
                SELECT *
                FROM provider_connections
                WHERE tenant_id = ? AND provider_id = ?
                """,
                (identity.tenant_id, provider_id),
            ).fetchone()
            response_json = canonical_json(
                {
                    "provider": _provider_projection(
                        pending_row,
                        descriptors[provider_id],
                    )
                }
            )
            database.execute(
                """
                INSERT INTO provider_enrollment_intents (
                    tenant_id, id, provider_id, requested_by_user_id,
                    owner_authorization_decision_id,
                    idempotency_key_hash, request_hash, command_json,
                    command_hash, api_response_json, state,
                    authority_status, authority_response_hash,
                    attempts, max_attempts, available_at,
                    lease_owner, lease_token, lease_until, fencing_token,
                    last_error_code, created_at, updated_at, completed_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    NULL, NULL, 0, ?, ?, NULL, NULL, NULL, 0,
                    ?, ?, ?, ?
                )
                """,
                (
                    identity.tenant_id,
                    intent_id,
                    provider_id,
                    identity.user_id,
                    owner_authorization_decision_id,
                    idempotency_digest,
                    request_hash,
                    command_json,
                    command_hash,
                    response_json,
                    "queued" if dispatch_configured else "blocked",
                    settings.provider_enrollment_max_attempts,
                    now,
                    (
                        None
                        if dispatch_configured
                        else "provider_authority_dispatch_not_configured"
                    ),
                    now,
                    now,
                    None if dispatch_configured else now,
                ),
            )

    return Response(
        content=response_json,
        status_code=http_status.HTTP_202_ACCEPTED,
        media_type="application/json",
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@router.post("/mimo-code/credential")
async def connect_local_mimo(
    request: Request,
    database: DatabaseDependency,
    identity: OwnerDependency,
    _auth: MutationAuthDependency,
) -> dict[str, Any]:
    body = await request.body()
    if not body or len(body) > _MAX_CREDENTIAL_BODY_BYTES:
        raise _error(
            http_status.HTTP_400_BAD_REQUEST,
            "mimo_api_key_required",
            "Введите API-ключ MiMo.",
        )
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        value = None
    api_key = value.get("apiKey") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or set(value) != {"apiKey"}
        or not isinstance(api_key, str)
    ):
        raise _error(
            http_status.HTTP_400_BAD_REQUEST,
            "mimo_api_key_required",
            "Введите API-ключ MiMo.",
        )
    settings: Settings = request.app.state.settings
    try:
        result = install_mimo_key(
            settings,
            api_key,
            tenant_id=identity.tenant_id,
        )
    except LocalProviderAuthorityError as error:
        raise _error(
            http_status.HTTP_400_BAD_REQUEST,
            error.code,
            error.message,
        ) from None
    return _save_local_connection(
        database,
        tenant_id=identity.tenant_id,
        provider_id="mimo-code",
        last_verified_at=result["last_verified_at"],
        evidence_hash=result["evidence_hash"],
    )


@router.post("/codex-cli/login-status")
def connect_local_codex(
    request: Request,
    database: DatabaseDependency,
    identity: OwnerDependency,
    _auth: MutationAuthDependency,
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    try:
        result = verify_codex_login(settings)
    except LocalProviderAuthorityError as error:
        raise _error(
            http_status.HTTP_409_CONFLICT,
            error.code,
            error.message,
        ) from None
    return _save_local_connection(
        database,
        tenant_id=identity.tenant_id,
        provider_id="codex-cli",
        last_verified_at=result["last_verified_at"],
        evidence_hash=result["evidence_hash"],
    )


__all__ = [
    "PROVIDER_ENROLLMENT_CAPABILITY",
    "PROVIDER_IDS",
    "router",
]
