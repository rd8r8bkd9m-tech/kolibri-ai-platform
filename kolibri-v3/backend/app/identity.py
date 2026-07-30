from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .config import Settings
from .database import get_database, transaction
from .schemas import (
    AgentProfile,
    AgentProfileUpdate,
    LoginRequest,
    MobileLoginRequest,
    MobileLogoutRequest,
    MobileRefreshRequest,
    MobileRegisterRequest,
    MobileTokenView,
    ModelSettingsUpdate,
    ProfilePatch,
    ProviderAdminContextView,
    RegisterRequest,
    SessionView,
    UserRole,
    UserSession,
    UserView,
)
from .mobile_auth import (
    MobileAuthFailure,
    MobileTokenPair,
    issue_device_session,
    require_bearer_session,
    revoke_refresh_token,
    rotate_refresh_token,
)
from .platform_authority import bind_platform_authority
from .security import (
    csrf_token_for_session,
    generate_session_token,
    hash_password,
    hash_session_token,
    require_csrf,
    require_mutation_auth,
    require_same_origin,
    verify_password,
)

router = APIRouter(prefix="/v1", tags=["identity"])

DatabaseDependency = Annotated[sqlite3.Connection, Depends(get_database)]
SameOriginDependency = Annotated[str, Depends(require_same_origin)]
CsrfDependency = Annotated[None, Depends(require_csrf)]
MutationAuthDependency = Annotated[None, Depends(require_mutation_auth)]

# Unknown users still pay one normal password-verification cost.
_DUMMY_PASSWORD_HASH = hash_password(uuid.uuid4().hex)
_LOGIN_WINDOW_SECONDS = 15 * 60
_LOGIN_BLOCK_SECONDS = 15 * 60
_LOGIN_MAX_FAILURES = 5


def _now() -> int:
    return int(time.time())


def _normalize_email(email: str) -> str:
    return email.strip().casefold()


def _login_throttle_key(email: str, settings: Settings) -> str:
    import hashlib
    import hmac

    return hmac.new(
        settings.csrf_secret,
        b"kolibri-v3-login-throttle-v1\0" + email.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _enforce_login_throttle(
    database: sqlite3.Connection,
    *,
    email: str,
    settings: Settings,
) -> None:
    row = database.execute(
        """
        SELECT blocked_until
        FROM auth_throttles
        WHERE key_hash = ?
        """,
        (_login_throttle_key(email, settings),),
    ).fetchone()
    if row is not None and int(row["blocked_until"] or 0) > _now():
        raise _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "login_temporarily_locked",
            "Too many sign-in attempts. Try again later.",
        )


def _record_login_failure(
    database: sqlite3.Connection,
    *,
    email: str,
    settings: Settings,
) -> None:
    now = _now()
    key_hash = _login_throttle_key(email, settings)
    with transaction(database, immediate=True):
        row = database.execute(
            """
            SELECT failure_count, window_started_at
            FROM auth_throttles
            WHERE key_hash = ?
            """,
            (key_hash,),
        ).fetchone()
        if row is None or int(row["window_started_at"]) <= now - _LOGIN_WINDOW_SECONDS:
            failures = 1
            window_started_at = now
        else:
            failures = int(row["failure_count"]) + 1
            window_started_at = int(row["window_started_at"])
        blocked_until = (
            now + _LOGIN_BLOCK_SECONDS
            if failures >= _LOGIN_MAX_FAILURES
            else None
        )
        database.execute(
            """
            INSERT INTO auth_throttles (
                key_hash, failure_count, window_started_at, blocked_until,
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key_hash) DO UPDATE SET
                failure_count = excluded.failure_count,
                window_started_at = excluded.window_started_at,
                blocked_until = excluded.blocked_until,
                updated_at = excluded.updated_at
            """,
            (
                key_hash,
                failures,
                window_started_at,
                blocked_until,
                now,
            ),
        )


def _clear_login_throttle(
    database: sqlite3.Connection,
    *,
    email: str,
    settings: Settings,
) -> None:
    database.execute(
        "DELETE FROM auth_throttles WHERE key_hash = ?",
        (_login_throttle_key(email, settings),),
    )


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _enforce_platform_access(
    database: sqlite3.Connection,
    identity: UserSession,
) -> None:
    # Lazy import keeps identity bootstrap independent from the admin router.
    from .platform_admin import PlatformPolicyError, enforce_identity_access

    try:
        enforce_identity_access(database, identity=identity)
    except PlatformPolicyError as exc:
        raise _error(exc.status_code, exc.code, exc.message) from exc


def _raw_session_token(request: Request, settings: Settings) -> str | None:
    token = request.cookies.get(settings.session_cookie_name)
    if not token or len(token) > 512 or not token.isascii():
        return None
    return token


def _record_event(
    database: sqlite3.Connection,
    *,
    event_type: str,
    actor_user_id: str | None,
    tenant_id: str | None,
    subject_user_id: str | None,
    metadata: dict[str, str] | None = None,
) -> None:
    database.execute(
        """
        INSERT INTO identity_events (
            id, event_type, actor_user_id, tenant_id, subject_user_id,
            created_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            event_type,
            actor_user_id,
            tenant_id,
            subject_user_id,
            _now(),
            json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True),
        ),
    )


def _issue_session(
    database: sqlite3.Connection,
    *,
    user_id: str,
    tenant_id: str,
    settings: Settings,
) -> str:
    token = generate_session_token()
    created_at = _now()
    database.execute(
        """
        INSERT INTO sessions (
            id, token_hash, user_id, tenant_id, created_at, expires_at, revoked_at
        ) VALUES (?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            str(uuid.uuid4()),
            hash_session_token(token),
            user_id,
            tenant_id,
            created_at,
            created_at + settings.session_ttl_seconds,
        ),
    )
    return token


def _revoke_request_session(
    database: sqlite3.Connection,
    request: Request,
    settings: Settings,
) -> None:
    token = _raw_session_token(request, settings)
    if token is None:
        return
    database.execute(
        """
        UPDATE sessions
        SET revoked_at = COALESCE(revoked_at, ?)
        WHERE token_hash = ?
        """,
        (_now(), hash_session_token(token)),
    )


def _set_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _set_session_cookies(
    response: Response,
    *,
    token: str,
    settings: Settings,
) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token_for_session(token, settings),
        max_age=settings.session_ttl_seconds,
        secure=settings.cookie_secure,
        httponly=False,
        samesite="lax",
        path="/",
    )
    _set_no_store(response)


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        settings.csrf_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=False,
        samesite="lax",
    )
    _set_no_store(response)


def _session_from_row(row: sqlite3.Row) -> UserSession:
    expires_at = (
        int(row["expires_at"])
        if "expires_at" in row.keys()
        else 0
    )
    authenticated_at = (
        int(row["authenticated_at"])
        if "authenticated_at" in row.keys()
        else 0
    )
    session_id = (
        str(row["session_id"])
        if "session_id" in row.keys()
        else ""
    )
    preferred_agent_profile = AgentProfile(row["preferred_agent_profile"])
    preferred_model_profile = (
        AgentProfile(str(row["preferred_model_profile"]))
        if "preferred_model_profile" in row.keys()
        and row["preferred_model_profile"] is not None
        else None
    )
    owns_selected_profile = (
        preferred_model_profile is not None
        and preferred_model_profile.value == preferred_agent_profile.value
    )
    preferred_model = (
        str(row["preferred_model"])
        if "preferred_model" in row.keys()
        and row["preferred_model"] is not None
        and owns_selected_profile
        else None
    )
    preferred_reasoning_effort = (
        str(row["preferred_reasoning_effort"])
        if "preferred_reasoning_effort" in row.keys()
        and row["preferred_reasoning_effort"] is not None
        and owns_selected_profile
        else None
    )
    preferred_service_tier = (
        str(row["preferred_service_tier"])
        if "preferred_service_tier" in row.keys()
        and row["preferred_service_tier"] is not None
        and owns_selected_profile
        else None
    )
    return UserSession(
        user_id=row["user_id"],
        tenant_id=row["tenant_id"],
        role=UserRole(row["role"]),
        preferred_agent_profile=preferred_agent_profile,
        email=row["email"],
        name=row["name"],
        preferred_model_profile=(
            preferred_model_profile if owns_selected_profile else None
        ),
        preferred_model=preferred_model,
        preferred_reasoning_effort=preferred_reasoning_effort,
        preferred_service_tier=preferred_service_tier,
        expires_at=expires_at,
        authenticated_at=authenticated_at,
        session_id=session_id,
    )


def _lookup_session(
    request: Request,
    database: sqlite3.Connection,
) -> tuple[UserSession, str] | None:
    settings: Settings = request.app.state.settings
    token = _raw_session_token(request, settings)
    if token is None:
        return None
    row = database.execute(
        """
        SELECT
            users.id AS user_id,
            users.tenant_id,
            users.email,
            users.name,
            users.role,
            users.preferred_agent_profile,
            model_preference.runtime_profile AS preferred_model_profile,
            model_preference.model_id AS preferred_model,
            model_preference.reasoning_effort AS preferred_reasoning_effort,
            model_preference.service_tier AS preferred_service_tier,
            sessions.expires_at
            , sessions.created_at AS authenticated_at
            , sessions.id AS session_id
        FROM sessions
        JOIN users
          ON users.id = sessions.user_id
         AND users.tenant_id = sessions.tenant_id
        LEFT JOIN user_model_preferences AS model_preference
          ON model_preference.tenant_id = users.tenant_id
         AND model_preference.user_id = users.id
         AND model_preference.runtime_profile =
             users.preferred_agent_profile
        WHERE sessions.token_hash = ?
          AND sessions.revoked_at IS NULL
          AND sessions.expires_at > ?
        LIMIT 1
        """,
        (hash_session_token(token), _now()),
    ).fetchone()
    if row is None:
        return None
    try:
        return _session_from_row(row), token
    except ValueError:
        return None


def require_user(
    request: Request,
    database: DatabaseDependency,
) -> UserSession:
    try:
        bearer_row = require_bearer_session(request, database)
    except MobileAuthFailure as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    if bearer_row is not None:
        try:
            identity = _session_from_row(bearer_row)
        except ValueError as exc:
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "mobile_access_token_invalid",
                "The access token is invalid or expired.",
            ) from exc
        identity = bind_platform_authority(database, identity)
        _enforce_platform_access(database, identity)
        return identity

    result = _lookup_session(request, database)
    if result is None:
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "authentication_required",
            "Authentication is required.",
        )
    identity = bind_platform_authority(database, result[0])
    _enforce_platform_access(database, identity)
    return identity


def require_owner(
    identity: Annotated[UserSession, Depends(require_user)],
) -> UserSession:
    if not identity.is_platform_owner:
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "owner_required",
            "Owner access is required.",
        )
    return identity


def _user_view(identity: UserSession) -> UserView:
    return UserView(
        id=identity.user_id,
        tenant_id=identity.tenant_id,
        email=identity.email,
        name=identity.name,
        role=identity.role,
        is_platform_owner=identity.is_platform_owner,
        capabilities=tuple(
            dict.fromkeys(
                (
                    *identity.platform_capabilities,
                    *identity.product_capabilities,
                )
            )
        ),
        entitlements=identity.product_entitlements,
        preferred_agent_profile=identity.preferred_agent_profile,
        preferred_model_profile=identity.preferred_model_profile,
        preferred_model=identity.preferred_model,
        preferred_reasoning_effort=identity.preferred_reasoning_effort,
        preferred_service_tier=identity.preferred_service_tier,
    )


def _fresh_user(
    database: sqlite3.Connection,
    *,
    user_id: str,
    tenant_id: str,
) -> UserSession:
    row = database.execute(
        """
        SELECT
            users.id AS user_id,
            users.tenant_id,
            users.email,
            users.name,
            users.role,
            users.preferred_agent_profile,
            model_preference.runtime_profile AS preferred_model_profile,
            model_preference.model_id AS preferred_model,
            model_preference.reasoning_effort AS preferred_reasoning_effort,
            model_preference.service_tier AS preferred_service_tier
        FROM users
        LEFT JOIN user_model_preferences AS model_preference
          ON model_preference.tenant_id = users.tenant_id
         AND model_preference.user_id = users.id
         AND model_preference.runtime_profile =
             users.preferred_agent_profile
        WHERE users.id = ? AND users.tenant_id = ?
        """,
        (user_id, tenant_id),
    ).fetchone()
    if row is None:
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "authentication_required",
            "Authentication is required.",
        )
    return bind_platform_authority(database, _session_from_row(row))


def _new_registration(
    payload: RegisterRequest,
    *,
    settings: Settings,
) -> tuple[UserSession, str, int]:
    created_at = _now()
    identity = UserSession(
        user_id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        role=UserRole.USER,
        preferred_agent_profile=AgentProfile.AUTO,
        email=_normalize_email(str(payload.email)),
        name=payload.name,
        expires_at=created_at + settings.session_ttl_seconds,
        authenticated_at=created_at,
    )
    return (
        identity,
        hash_password(payload.password.get_secret_value()),
        created_at,
    )


def _insert_registered_account(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    password_digest: str,
    created_at: int,
) -> None:
    if database.execute(
        "SELECT 1 FROM users WHERE email_normalized = ? LIMIT 1",
        (identity.email,),
    ).fetchone():
        raise _error(
            status.HTTP_409_CONFLICT,
            "email_already_registered",
            "An account already exists for this email.",
        )
    database.execute(
        "INSERT INTO tenants (id, name, created_at) VALUES (?, ?, ?)",
        (
            identity.tenant_id,
            f"{identity.name} workspace"[:160],
            created_at,
        ),
    )
    database.execute(
        """
        INSERT INTO users (
            id, tenant_id, email_normalized, email, name, role,
            preferred_agent_profile, password_hash, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'auto', ?, ?, ?)
        """,
        (
            identity.user_id,
            identity.tenant_id,
            identity.email,
            identity.email,
            identity.name,
            identity.role.value,
            password_digest,
            created_at,
            created_at,
        ),
    )
    _record_event(
        database,
        event_type="user_registered",
        actor_user_id=identity.user_id,
        tenant_id=identity.tenant_id,
        subject_user_id=identity.user_id,
    )


@router.post(
    "/auth/register",
    response_model=SessionView,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    database: DatabaseDependency,
    _origin: SameOriginDependency,
) -> SessionView:
    settings: Settings = request.app.state.settings
    identity, password_digest, created_at = _new_registration(
        payload,
        settings=settings,
    )

    try:
        with transaction(database, immediate=True):
            _insert_registered_account(
                database,
                identity=identity,
                password_digest=password_digest,
                created_at=created_at,
            )
            _revoke_request_session(database, request, settings)
            token = _issue_session(
                database,
                user_id=identity.user_id,
                tenant_id=identity.tenant_id,
                settings=settings,
            )
    except sqlite3.IntegrityError as exc:
        raise _error(
            status.HTTP_409_CONFLICT,
            "registration_conflict",
            "The account could not be registered.",
        ) from exc

    _set_session_cookies(response, token=token, settings=settings)
    return SessionView(authenticated=True, user=_user_view(identity))


def _authenticate_password(
    database: sqlite3.Connection,
    *,
    email_value: str,
    password: str,
    settings: Settings,
) -> UserSession:
    email = _normalize_email(email_value)
    _enforce_login_throttle(database, email=email, settings=settings)
    row = database.execute(
        """
        SELECT
            users.id AS user_id,
            users.tenant_id,
            users.email,
            users.name,
            users.role,
            users.preferred_agent_profile,
            model_preference.runtime_profile AS preferred_model_profile,
            model_preference.model_id AS preferred_model,
            model_preference.reasoning_effort AS preferred_reasoning_effort,
            model_preference.service_tier AS preferred_service_tier,
            users.password_hash
        FROM users
        LEFT JOIN user_model_preferences AS model_preference
          ON model_preference.tenant_id = users.tenant_id
         AND model_preference.user_id = users.id
         AND model_preference.runtime_profile =
             users.preferred_agent_profile
        WHERE users.email_normalized = ?
        LIMIT 1
        """,
        (email,),
    ).fetchone()

    password_hash = row["password_hash"] if row is not None else _DUMMY_PASSWORD_HASH
    if not verify_password(password, password_hash) or row is None:
        _record_login_failure(database, email=email, settings=settings)
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "Email or password is incorrect.",
        )
    try:
        identity = bind_platform_authority(
            database,
            _session_from_row(row),
        )
    except ValueError as exc:
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "Email or password is incorrect.",
        ) from exc
    _enforce_platform_access(database, identity)
    _clear_login_throttle(database, email=email, settings=settings)
    return identity


@router.post("/auth/login", response_model=SessionView)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    database: DatabaseDependency,
    _origin: SameOriginDependency,
) -> SessionView:
    settings: Settings = request.app.state.settings
    identity = _authenticate_password(
        database,
        email_value=str(payload.email),
        password=payload.password.get_secret_value(),
        settings=settings,
    )

    with transaction(database, immediate=True):
        current_session = _lookup_session(request, database)
        if (
            current_session is not None
            and current_session[0].user_id == identity.user_id
            and current_session[0].tenant_id == identity.tenant_id
        ):
            token = current_session[1]
        else:
            # Logging in from another tab or device must not revoke an already
            # valid session for the same account. Revoke only a different
            # subject that happens to be present in this request context.
            if current_session is not None:
                _revoke_request_session(database, request, settings)
            token = _issue_session(
                database,
                user_id=identity.user_id,
                tenant_id=identity.tenant_id,
                settings=settings,
            )
        _record_event(
            database,
            event_type="login_succeeded",
            actor_user_id=identity.user_id,
            tenant_id=identity.tenant_id,
            subject_user_id=identity.user_id,
        )

    _set_session_cookies(response, token=token, settings=settings)
    return SessionView(authenticated=True, user=_user_view(identity))


def _mobile_token_view(
    pair: MobileTokenPair,
    identity: UserSession,
) -> MobileTokenView:
    return MobileTokenView(
        accessToken=pair.access_token,
        accessExpiresAt=datetime.fromtimestamp(
            pair.access_expires_at,
            tz=timezone.utc,
        ),
        refreshToken=pair.refresh_token,
        refreshExpiresAt=datetime.fromtimestamp(
            pair.refresh_expires_at,
            tz=timezone.utc,
        ),
        deviceSessionId=pair.device_session_id,
        user=_user_view(identity),
    )


def _raise_mobile_auth_failure(error: MobileAuthFailure) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
        headers={"WWW-Authenticate": "Bearer"},
    ) from error


@router.post(
    "/mobile/auth/register",
    response_model=MobileTokenView,
    status_code=status.HTTP_201_CREATED,
)
def mobile_register(
    payload: MobileRegisterRequest,
    request: Request,
    database: DatabaseDependency,
) -> MobileTokenView:
    settings: Settings = request.app.state.settings
    identity, password_digest, created_at = _new_registration(
        payload,
        settings=settings,
    )
    try:
        with transaction(database, immediate=True):
            _insert_registered_account(
                database,
                identity=identity,
                password_digest=password_digest,
                created_at=created_at,
            )
            pair = issue_device_session(
                database,
                user_id=identity.user_id,
                tenant_id=identity.tenant_id,
                platform=payload.device.platform.value,
                device_name=payload.device.device_name,
                app_version=payload.device.app_version,
                settings=settings,
                event_type="device_registered",
            )
    except sqlite3.IntegrityError as exc:
        raise _error(
            status.HTTP_409_CONFLICT,
            "registration_conflict",
            "The account could not be registered.",
        ) from exc
    return _mobile_token_view(pair, identity)


@router.post("/mobile/auth/login", response_model=MobileTokenView)
def mobile_login(
    payload: MobileLoginRequest,
    request: Request,
    database: DatabaseDependency,
) -> MobileTokenView:
    settings: Settings = request.app.state.settings
    identity = _authenticate_password(
        database,
        email_value=str(payload.email),
        password=payload.password.get_secret_value(),
        settings=settings,
    )
    with transaction(database, immediate=True):
        pair = issue_device_session(
            database,
            user_id=identity.user_id,
            tenant_id=identity.tenant_id,
            platform=payload.device.platform.value,
            device_name=payload.device.device_name,
            app_version=payload.device.app_version,
            settings=settings,
            event_type="device_login",
        )
    return _mobile_token_view(pair, identity)


@router.post("/mobile/auth/refresh", response_model=MobileTokenView)
def mobile_refresh(
    payload: MobileRefreshRequest,
    request: Request,
    database: DatabaseDependency,
) -> MobileTokenView:
    settings: Settings = request.app.state.settings
    try:
        pair = rotate_refresh_token(
            database,
            refresh_token=payload.refresh_token.get_secret_value(),
            settings=settings,
        )
    except MobileAuthFailure as error:
        _raise_mobile_auth_failure(error)
    identity = _fresh_user(
        database,
        user_id=pair.user_id,
        tenant_id=pair.tenant_id,
    )
    _enforce_platform_access(database, identity)
    return _mobile_token_view(pair, identity)


@router.get("/mobile/auth/session", response_model=SessionView)
def mobile_session(
    request: Request,
    database: DatabaseDependency,
) -> SessionView:
    try:
        row = require_bearer_session(request, database)
    except MobileAuthFailure as error:
        _raise_mobile_auth_failure(error)
    if row is None:
        _raise_mobile_auth_failure(
            MobileAuthFailure(
                status.HTTP_401_UNAUTHORIZED,
                "mobile_access_token_required",
                "A native access token is required.",
            )
        )
    try:
        identity = bind_platform_authority(
            database,
            _session_from_row(row),
        )
    except ValueError as exc:
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "mobile_access_token_invalid",
            "The access token is invalid or expired.",
        ) from exc
    _enforce_platform_access(database, identity)
    return SessionView(authenticated=True, user=_user_view(identity))


@router.post("/mobile/auth/logout", response_model=SessionView)
def mobile_logout(
    payload: MobileLogoutRequest,
    database: DatabaseDependency,
) -> SessionView:
    revoke_refresh_token(
        database,
        refresh_token=payload.refresh_token.get_secret_value(),
    )
    return SessionView(authenticated=False, user=None)


def _provider_admin_context(
    request: Request,
    database: sqlite3.Connection,
    *,
    csrf_verified: bool,
) -> ProviderAdminContextView:
    result = _lookup_session(request, database)
    if result is None:
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "owner_required",
            "Owner access is required.",
        )
    identity = bind_platform_authority(database, result[0])
    if not identity.is_platform_owner:
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "owner_required",
            "Owner access is required.",
        )
    return ProviderAdminContextView(
        subjectId=identity.user_id,
        tenantId=identity.tenant_id,
        csrfVerified=csrf_verified,
        expiresAt=datetime.fromtimestamp(
            identity.expires_at,
            tz=timezone.utc,
        ),
    )


@router.get(
    "/internal/provider-admin-context",
    response_model=ProviderAdminContextView,
    include_in_schema=False,
)
def get_provider_admin_context(
    request: Request,
    response: Response,
    database: DatabaseDependency,
) -> ProviderAdminContextView:
    _set_no_store(response)
    return _provider_admin_context(
        request,
        database,
        csrf_verified=False,
    )


@router.post(
    "/internal/provider-admin-context",
    response_model=ProviderAdminContextView,
    include_in_schema=False,
)
def authorize_provider_admin_mutation(
    request: Request,
    response: Response,
    database: DatabaseDependency,
    _csrf: CsrfDependency,
) -> ProviderAdminContextView:
    _set_no_store(response)
    return _provider_admin_context(
        request,
        database,
        csrf_verified=True,
    )


@router.get("/session", response_model=SessionView)
@router.get("/auth/session", response_model=SessionView, include_in_schema=False)
def session(
    request: Request,
    response: Response,
    database: DatabaseDependency,
) -> SessionView:
    settings: Settings = request.app.state.settings
    result = _lookup_session(request, database)
    if result is None:
        _clear_session_cookies(response, settings)
        return SessionView(authenticated=False, user=None)

    identity, token = result
    identity = bind_platform_authority(database, identity)
    _enforce_platform_access(database, identity)
    _set_session_cookies(response, token=token, settings=settings)
    return SessionView(authenticated=True, user=_user_view(identity))


@router.post("/auth/logout", response_model=SessionView)
def logout(
    request: Request,
    response: Response,
    database: DatabaseDependency,
    identity: Annotated[UserSession, Depends(require_user)],
    _csrf: CsrfDependency,
) -> SessionView:
    settings: Settings = request.app.state.settings
    with transaction(database, immediate=True):
        _revoke_request_session(database, request, settings)
        _record_event(
            database,
            event_type="logout_succeeded",
            actor_user_id=identity.user_id,
            tenant_id=identity.tenant_id,
            subject_user_id=identity.user_id,
        )
    _clear_session_cookies(response, settings)
    return SessionView(authenticated=False, user=None)


@router.get("/profile", response_model=UserView)
def get_profile(
    identity: Annotated[UserSession, Depends(require_user)],
) -> UserView:
    return _user_view(identity)


def _validate_profile_change(
    request: Request,
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    profile: AgentProfile,
) -> None:
    # Imported lazily to keep identity dependencies one-way at module import
    # time while the catalog router reuses require_user.
    from .model_catalog import (
        validate_model_selection,
        validate_profile_selection,
    )

    if profile is AgentProfile.AUTO:
        validate_profile_selection(
            request,
            database,
            tenant_id=identity.tenant_id,
            profile=profile,
        )
        return
    saved = database.execute(
        """
        SELECT model_id, reasoning_effort, service_tier
        FROM user_model_preferences
        WHERE tenant_id = ?
          AND user_id = ?
          AND runtime_profile = ?
        """,
        (identity.tenant_id, identity.user_id, profile.value),
    ).fetchone()
    if saved is None:
        validate_profile_selection(
            request,
            database,
            tenant_id=identity.tenant_id,
            profile=profile,
        )
        return
    # A stored preference is only a candidate. Revalidate it against the live
    # descriptor, tenant connection and current catalog before making it active
    # again; stale settings never silently reactivate or select another model.
    validate_model_selection(
        request,
        database,
        tenant_id=identity.tenant_id,
        profile=profile,
        model=str(saved["model_id"]),
        reasoning_effort=(
            str(saved["reasoning_effort"])
            if saved["reasoning_effort"] is not None
            else None
        ),
        service_tier=(
            str(saved["service_tier"])
            if saved["service_tier"] is not None
            else None
        ),
    )


def _update_profile(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    name: str | None = None,
    preferred_agent_profile: AgentProfile | None = None,
) -> UserView:
    assignments: list[str] = []
    values: list[object] = []
    metadata: dict[str, str] = {}
    if name is not None:
        assignments.append("name = ?")
        values.append(name)
        metadata["field_name"] = "updated"
    if preferred_agent_profile is not None:
        assignments.append("preferred_agent_profile = ?")
        values.append(preferred_agent_profile.value)
        metadata["preferred_agent_profile"] = preferred_agent_profile.value
        for legacy_column, preference_column in (
            ("preferred_model", "model_id"),
            ("preferred_reasoning_effort", "reasoning_effort"),
            ("preferred_service_tier", "service_tier"),
        ):
            assignments.append(
                f"""
                {legacy_column} = (
                    SELECT preference.{preference_column}
                    FROM user_model_preferences AS preference
                    WHERE preference.tenant_id = ?
                      AND preference.user_id = ?
                      AND preference.runtime_profile = ?
                )
                """
            )
            values.extend(
                (
                    identity.tenant_id,
                    identity.user_id,
                    preferred_agent_profile.value,
                )
            )
    assignments.append("updated_at = ?")
    values.append(_now())
    values.extend((identity.user_id, identity.tenant_id))

    with transaction(database, immediate=True):
        current = database.execute(
            """
            SELECT name, preferred_agent_profile
            FROM users
            WHERE id = ? AND tenant_id = ?
            """,
            (identity.user_id, identity.tenant_id),
        ).fetchone()
        if current is None:
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "authentication_required",
                "Authentication is required.",
            )
        name_unchanged = name is None or str(current["name"]) == name
        profile_unchanged = (
            preferred_agent_profile is None
            or str(current["preferred_agent_profile"])
            == preferred_agent_profile.value
        )
        if name_unchanged and profile_unchanged:
            return _user_view(
                _fresh_user(
                    database,
                    user_id=identity.user_id,
                    tenant_id=identity.tenant_id,
                )
            )
        if preferred_agent_profile is AgentProfile.AUTO:
            database.execute(
                """
                DELETE FROM user_model_preferences
                WHERE tenant_id = ?
                  AND user_id = ?
                  AND runtime_profile = 'auto'
                """,
                (identity.tenant_id, identity.user_id),
            )
        cursor = database.execute(
            f"""
            UPDATE users
            SET {", ".join(assignments)}
            WHERE id = ? AND tenant_id = ?
            """,
            tuple(values),
        )
        if cursor.rowcount != 1:
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "authentication_required",
                "Authentication is required.",
            )
        _record_event(
            database,
            event_type="profile_updated",
            actor_user_id=identity.user_id,
            tenant_id=identity.tenant_id,
            subject_user_id=identity.user_id,
            metadata=metadata,
        )
    return _user_view(
        _fresh_user(
            database,
            user_id=identity.user_id,
            tenant_id=identity.tenant_id,
        )
    )


@router.patch("/profile", response_model=UserView)
def patch_profile(
    payload: ProfilePatch,
    request: Request,
    database: DatabaseDependency,
    identity: Annotated[UserSession, Depends(require_user)],
    _auth: MutationAuthDependency,
) -> UserView:
    if payload.preferred_agent_profile is not None:
        _validate_profile_change(
            request,
            database,
            identity=identity,
            profile=payload.preferred_agent_profile,
        )
    return _update_profile(
        database,
        identity=identity,
        name=payload.name,
        preferred_agent_profile=payload.preferred_agent_profile,
    )


@router.put("/profile/agent-profile", response_model=UserView)
def put_agent_profile(
    payload: AgentProfileUpdate,
    request: Request,
    database: DatabaseDependency,
    identity: Annotated[UserSession, Depends(require_user)],
    _auth: MutationAuthDependency,
) -> UserView:
    _validate_profile_change(
        request,
        database,
        identity=identity,
        profile=payload.profile,
    )
    return _update_profile(
        database,
        identity=identity,
        preferred_agent_profile=payload.profile,
    )


def _save_model_settings(
    database: sqlite3.Connection,
    *,
    identity: UserSession,
    payload: ModelSettingsUpdate,
    selection_supported: bool,
) -> UserView:
    now = _now()
    profile_id = payload.profile.value
    store_selection = (
        payload.profile is not AgentProfile.AUTO and selection_supported
    )
    model = payload.model if store_selection else None
    reasoning_effort = (
        payload.reasoning_effort if store_selection else None
    )
    service_tier = payload.service_tier if store_selection else None
    with transaction(database, immediate=True):
        current = database.execute(
            """
            SELECT preferred_agent_profile, preferred_model,
                   preferred_reasoning_effort, preferred_service_tier
            FROM users
            WHERE id = ? AND tenant_id = ?
            """,
            (identity.user_id, identity.tenant_id),
        ).fetchone()
        if current is None:
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "authentication_required",
                "Authentication is required.",
            )
        saved = database.execute(
            """
            SELECT model_id, reasoning_effort, service_tier
            FROM user_model_preferences
            WHERE tenant_id = ?
              AND user_id = ?
              AND runtime_profile = ?
            """,
            (identity.tenant_id, identity.user_id, profile_id),
        ).fetchone()
        saved_matches = (
            saved is not None
            and str(saved["model_id"]) == model
            and saved["reasoning_effort"] == reasoning_effort
            and saved["service_tier"] == service_tier
            if store_selection
            else saved is None
        )
        current_matches = (
            str(current["preferred_agent_profile"]) == profile_id
            and current["preferred_model"] == model
            and current["preferred_reasoning_effort"] == reasoning_effort
            and current["preferred_service_tier"] == service_tier
        )
        if saved_matches and current_matches:
            return _user_view(
                _fresh_user(
                    database,
                    user_id=identity.user_id,
                    tenant_id=identity.tenant_id,
                )
            )
        if store_selection:
            database.execute(
                """
                INSERT INTO user_model_preferences (
                    tenant_id, user_id, runtime_profile, model_id,
                    reasoning_effort, service_tier, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, user_id, runtime_profile)
                DO UPDATE SET
                    model_id = excluded.model_id,
                    reasoning_effort = excluded.reasoning_effort,
                    service_tier = excluded.service_tier,
                    updated_at = excluded.updated_at
                """,
                (
                    identity.tenant_id,
                    identity.user_id,
                    profile_id,
                    model,
                    reasoning_effort,
                    service_tier,
                    now,
                ),
            )
        else:
            database.execute(
                """
                DELETE FROM user_model_preferences
                WHERE tenant_id = ?
                  AND user_id = ?
                  AND runtime_profile = ?
                """,
                (identity.tenant_id, identity.user_id, profile_id),
            )
        cursor = database.execute(
            """
            UPDATE users
            SET preferred_agent_profile = ?,
                preferred_model = ?,
                preferred_reasoning_effort = ?,
                preferred_service_tier = ?,
                updated_at = ?
            WHERE id = ? AND tenant_id = ?
            """,
            (
                profile_id,
                model,
                reasoning_effort,
                service_tier,
                now,
                identity.user_id,
                identity.tenant_id,
            ),
        )
        if cursor.rowcount != 1:
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "authentication_required",
                "Authentication is required.",
            )
        _record_event(
            database,
            event_type="profile_updated",
            actor_user_id=identity.user_id,
            tenant_id=identity.tenant_id,
            subject_user_id=identity.user_id,
            metadata={
                "preferred_agent_profile": profile_id,
                "preferred_model": model or "runtime-default",
                "preferred_reasoning_effort": (
                    reasoning_effort or "model-default"
                ),
                "preferred_service_tier": service_tier or "standard",
            },
        )
    return _user_view(
        _fresh_user(
            database,
            user_id=identity.user_id,
            tenant_id=identity.tenant_id,
        )
    )


@router.put("/profile/model-settings", response_model=UserView)
def put_model_settings(
    payload: ModelSettingsUpdate,
    request: Request,
    database: DatabaseDependency,
    identity: Annotated[UserSession, Depends(require_user)],
    _auth: MutationAuthDependency,
) -> UserView:
    # Imported lazily to keep identity dependencies one-way at module import
    # time while the catalog router reuses require_user.
    from .model_catalog import validate_model_selection

    selected = validate_model_selection(
        request,
        database,
        tenant_id=identity.tenant_id,
        profile=payload.profile,
        model=payload.model or (
            "auto" if payload.profile is AgentProfile.AUTO else None
        ),
        reasoning_effort=payload.reasoning_effort,
        service_tier=payload.service_tier,
    )
    return _save_model_settings(
        database,
        identity=identity,
        payload=payload,
        selection_supported=selected.selection_supported,
    )
