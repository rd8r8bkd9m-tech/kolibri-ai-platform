from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass

from fastapi import Request, status

from .config import Settings
from .database import transaction

_ACCESS_TOKEN_PREFIX = "kma_"
_REFRESH_TOKEN_PREFIX = "kmr_"
_MAX_TOKEN_LENGTH = 512


@dataclass(frozen=True, slots=True)
class MobileAuthFailure(Exception):
    status_code: int
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class MobileTokenPair:
    access_token: str
    access_expires_at: int
    refresh_token: str
    refresh_expires_at: int
    device_session_id: str
    user_id: str
    tenant_id: str


def _now() -> int:
    return int(time.time())


def _new_token(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(48)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _validated_token(value: str, *, prefix: str) -> str:
    if (
        not value
        or len(value) > _MAX_TOKEN_LENGTH
        or not value.isascii()
        or not value.startswith(prefix)
    ):
        raise MobileAuthFailure(
            status.HTTP_401_UNAUTHORIZED,
            "mobile_token_invalid",
            "The device session token is invalid.",
        )
    return value


def bearer_token_from_request(request: Request) -> str | None:
    raw_header = request.headers.get("authorization")
    if raw_header is None:
        return None
    if (
        len(raw_header) > _MAX_TOKEN_LENGTH + 16
        or not raw_header.isascii()
    ):
        raise MobileAuthFailure(
            status.HTTP_401_UNAUTHORIZED,
            "mobile_access_token_invalid",
            "The access token is invalid or expired.",
        )
    parts = raw_header.split()
    if len(parts) != 2 or parts[0].casefold() != "bearer":
        raise MobileAuthFailure(
            status.HTTP_401_UNAUTHORIZED,
            "mobile_access_token_invalid",
            "The access token is invalid or expired.",
        )
    return _validated_token(parts[1], prefix=_ACCESS_TOKEN_PREFIX)


def lookup_access_session(
    database: sqlite3.Connection,
    access_token: str,
    *,
    now: int | None = None,
) -> sqlite3.Row | None:
    checked_at = _now() if now is None else now
    try:
        token = _validated_token(access_token, prefix=_ACCESS_TOKEN_PREFIX)
    except MobileAuthFailure:
        return None
    return database.execute(
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
            access.expires_at,
            device.created_at AS authenticated_at,
            device.id AS session_id
        FROM mobile_access_tokens AS access
        JOIN mobile_device_sessions AS device
          ON device.id = access.device_session_id
         AND device.user_id = access.user_id
         AND device.tenant_id = access.tenant_id
        JOIN users
          ON users.id = access.user_id
         AND users.tenant_id = access.tenant_id
        LEFT JOIN user_model_preferences AS model_preference
          ON model_preference.tenant_id = users.tenant_id
         AND model_preference.user_id = users.id
         AND model_preference.runtime_profile =
             users.preferred_agent_profile
        WHERE access.token_hash = ?
          AND access.revoked_at IS NULL
          AND access.expires_at > ?
          AND device.revoked_at IS NULL
          AND device.expires_at > ?
        LIMIT 1
        """,
        (_token_hash(token), checked_at, checked_at),
    ).fetchone()


def require_bearer_session(
    request: Request,
    database: sqlite3.Connection,
) -> sqlite3.Row | None:
    token = bearer_token_from_request(request)
    if token is None:
        return None
    row = lookup_access_session(database, token)
    if row is None:
        raise MobileAuthFailure(
            status.HTTP_401_UNAUTHORIZED,
            "mobile_access_token_invalid",
            "The access token is invalid or expired.",
        )
    return row


def _record_mobile_event(
    database: sqlite3.Connection,
    *,
    event_type: str,
    device_session_id: str,
    user_id: str,
    tenant_id: str,
    now: int,
    metadata: dict[str, str] | None = None,
) -> None:
    database.execute(
        """
        INSERT INTO mobile_auth_events (
            id, event_type, device_session_id, user_id, tenant_id,
            created_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            event_type,
            device_session_id,
            user_id,
            tenant_id,
            now,
            json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True),
        ),
    )


def issue_device_session(
    database: sqlite3.Connection,
    *,
    user_id: str,
    tenant_id: str,
    platform: str,
    device_name: str,
    app_version: str,
    settings: Settings,
    event_type: str,
) -> MobileTokenPair:
    now = _now()
    device_session_id = str(uuid.uuid4())
    refresh_id = str(uuid.uuid4())
    access_id = str(uuid.uuid4())
    access_token = _new_token(_ACCESS_TOKEN_PREFIX)
    refresh_token = _new_token(_REFRESH_TOKEN_PREFIX)
    access_expires_at = now + settings.mobile_access_ttl_seconds
    refresh_expires_at = now + settings.mobile_refresh_ttl_seconds

    database.execute(
        """
        INSERT INTO mobile_device_sessions (
            id, user_id, tenant_id, platform, device_name, app_version,
            created_at, last_refreshed_at, expires_at, revoked_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            device_session_id,
            user_id,
            tenant_id,
            platform,
            device_name,
            app_version,
            now,
            now,
            refresh_expires_at,
        ),
    )
    database.execute(
        """
        INSERT INTO mobile_refresh_tokens (
            id, device_session_id, token_hash, generation, created_at,
            expires_at, consumed_at, revoked_at, replaced_by_id
        ) VALUES (?, ?, ?, 0, ?, ?, NULL, NULL, NULL)
        """,
        (
            refresh_id,
            device_session_id,
            _token_hash(refresh_token),
            now,
            refresh_expires_at,
        ),
    )
    database.execute(
        """
        INSERT INTO mobile_access_tokens (
            id, device_session_id, token_hash, user_id, tenant_id,
            created_at, expires_at, revoked_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            access_id,
            device_session_id,
            _token_hash(access_token),
            user_id,
            tenant_id,
            now,
            access_expires_at,
        ),
    )
    _record_mobile_event(
        database,
        event_type=event_type,
        device_session_id=device_session_id,
        user_id=user_id,
        tenant_id=tenant_id,
        now=now,
        metadata={"platform": platform, "app_version": app_version},
    )
    return MobileTokenPair(
        access_token=access_token,
        access_expires_at=access_expires_at,
        refresh_token=refresh_token,
        refresh_expires_at=refresh_expires_at,
        device_session_id=device_session_id,
        user_id=user_id,
        tenant_id=tenant_id,
    )


def _revoke_device_family(
    database: sqlite3.Connection,
    *,
    device_session_id: str,
    now: int,
) -> None:
    database.execute(
        """
        UPDATE mobile_device_sessions
        SET revoked_at = COALESCE(revoked_at, ?)
        WHERE id = ?
        """,
        (now, device_session_id),
    )
    database.execute(
        """
        UPDATE mobile_refresh_tokens
        SET revoked_at = COALESCE(revoked_at, ?)
        WHERE device_session_id = ?
        """,
        (now, device_session_id),
    )
    database.execute(
        """
        UPDATE mobile_access_tokens
        SET revoked_at = COALESCE(revoked_at, ?)
        WHERE device_session_id = ?
        """,
        (now, device_session_id),
    )


def rotate_refresh_token(
    database: sqlite3.Connection,
    *,
    refresh_token: str,
    settings: Settings,
) -> MobileTokenPair:
    token = _validated_token(refresh_token, prefix=_REFRESH_TOKEN_PREFIX)
    now = _now()
    result: MobileTokenPair | None = None
    failure: MobileAuthFailure | None = None

    with transaction(database, immediate=True):
        row = database.execute(
            """
            SELECT
                refresh.id AS refresh_id,
                refresh.device_session_id,
                refresh.generation,
                refresh.expires_at AS refresh_expires_at,
                refresh.consumed_at,
                refresh.revoked_at AS refresh_revoked_at,
                device.user_id,
                device.tenant_id,
                device.expires_at AS device_expires_at,
                device.revoked_at AS device_revoked_at
            FROM mobile_refresh_tokens AS refresh
            JOIN mobile_device_sessions AS device
              ON device.id = refresh.device_session_id
            WHERE refresh.token_hash = ?
            LIMIT 1
            """,
            (_token_hash(token),),
        ).fetchone()

        if row is None:
            failure = MobileAuthFailure(
                status.HTTP_401_UNAUTHORIZED,
                "mobile_refresh_token_invalid",
                "The refresh token is invalid or expired.",
            )
        elif row["consumed_at"] is not None:
            device_session_id = str(row["device_session_id"])
            user_id = str(row["user_id"])
            tenant_id = str(row["tenant_id"])
            _revoke_device_family(
                database,
                device_session_id=device_session_id,
                now=now,
            )
            _record_mobile_event(
                database,
                event_type="refresh_replay_detected",
                device_session_id=device_session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                now=now,
            )
            failure = MobileAuthFailure(
                status.HTTP_401_UNAUTHORIZED,
                "mobile_refresh_token_reused",
                "The device session was revoked because a refresh token was reused.",
            )
        elif (
            row["refresh_revoked_at"] is not None
            or int(row["refresh_expires_at"]) <= now
            or row["device_revoked_at"] is not None
            or int(row["device_expires_at"]) <= now
        ):
            failure = MobileAuthFailure(
                status.HTTP_401_UNAUTHORIZED,
                "mobile_refresh_token_invalid",
                "The refresh token is invalid or expired.",
            )
        else:
            device_session_id = str(row["device_session_id"])
            user_id = str(row["user_id"])
            tenant_id = str(row["tenant_id"])
            next_generation = int(row["generation"]) + 1
            next_refresh_id = str(uuid.uuid4())
            next_access_id = str(uuid.uuid4())
            next_refresh = _new_token(_REFRESH_TOKEN_PREFIX)
            next_access = _new_token(_ACCESS_TOKEN_PREFIX)
            access_expires_at = now + settings.mobile_access_ttl_seconds
            refresh_expires_at = min(
                int(row["device_expires_at"]),
                now + settings.mobile_refresh_ttl_seconds,
            )

            database.execute(
                """
                INSERT INTO mobile_refresh_tokens (
                    id, device_session_id, token_hash, generation, created_at,
                    expires_at, consumed_at, revoked_at, replaced_by_id
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
                """,
                (
                    next_refresh_id,
                    device_session_id,
                    _token_hash(next_refresh),
                    next_generation,
                    now,
                    refresh_expires_at,
                ),
            )
            updated = database.execute(
                """
                UPDATE mobile_refresh_tokens
                SET consumed_at = ?, replaced_by_id = ?
                WHERE id = ? AND consumed_at IS NULL AND revoked_at IS NULL
                """,
                (now, next_refresh_id, str(row["refresh_id"])),
            )
            if updated.rowcount != 1:
                raise RuntimeError("mobile refresh rotation lost its transaction fence")
            database.execute(
                """
                UPDATE mobile_access_tokens
                SET revoked_at = COALESCE(revoked_at, ?)
                WHERE device_session_id = ?
                """,
                (now, device_session_id),
            )
            database.execute(
                """
                INSERT INTO mobile_access_tokens (
                    id, device_session_id, token_hash, user_id, tenant_id,
                    created_at, expires_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    next_access_id,
                    device_session_id,
                    _token_hash(next_access),
                    user_id,
                    tenant_id,
                    now,
                    access_expires_at,
                ),
            )
            database.execute(
                """
                UPDATE mobile_device_sessions
                SET last_refreshed_at = ?
                WHERE id = ? AND revoked_at IS NULL
                """,
                (now, device_session_id),
            )
            _record_mobile_event(
                database,
                event_type="token_refreshed",
                device_session_id=device_session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                now=now,
                metadata={"generation": str(next_generation)},
            )
            result = MobileTokenPair(
                access_token=next_access,
                access_expires_at=access_expires_at,
                refresh_token=next_refresh,
                refresh_expires_at=refresh_expires_at,
                device_session_id=device_session_id,
                user_id=user_id,
                tenant_id=tenant_id,
            )

    if failure is not None:
        raise failure
    if result is None:
        raise RuntimeError("mobile refresh rotation produced no result")
    return result


def revoke_refresh_token(
    database: sqlite3.Connection,
    *,
    refresh_token: str,
) -> bool:
    try:
        token = _validated_token(refresh_token, prefix=_REFRESH_TOKEN_PREFIX)
    except MobileAuthFailure:
        return False
    now = _now()
    revoked = False
    with transaction(database, immediate=True):
        row = database.execute(
            """
            SELECT
                refresh.device_session_id,
                device.user_id,
                device.tenant_id,
                device.revoked_at
            FROM mobile_refresh_tokens AS refresh
            JOIN mobile_device_sessions AS device
              ON device.id = refresh.device_session_id
            WHERE refresh.token_hash = ?
            LIMIT 1
            """,
            (_token_hash(token),),
        ).fetchone()
        if row is not None and row["revoked_at"] is None:
            device_session_id = str(row["device_session_id"])
            user_id = str(row["user_id"])
            tenant_id = str(row["tenant_id"])
            _revoke_device_family(
                database,
                device_session_id=device_session_id,
                now=now,
            )
            _record_mobile_event(
                database,
                event_type="device_logout",
                device_session_id=device_session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                now=now,
            )
            revoked = True
    return revoked
