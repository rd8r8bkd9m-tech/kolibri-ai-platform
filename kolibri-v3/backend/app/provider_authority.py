"""Strict, secretless transport to Provider Execution Authority.

Only a versioned enrollment intent crosses this boundary.  MiMo credentials,
Codex CLI login material, provider responses, paths and authorization URLs
remain on Primary and are neither accepted nor returned by this client.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import hmac
import ipaddress
import json
import os
import re
import stat
from typing import Any
from urllib.parse import urlsplit
import uuid

import httpx

from .chat.service import canonical_command_hash


PROVIDER_ENROLLMENT_AUTHORITY_PATH = (
    "/v1/runtime/product-provider-enrollment-intents"
)
_MAX_COMMAND_BYTES = 64 * 1024
_MAX_RESPONSE_BYTES = 64 * 1024
_SECRET_PATTERN = re.compile(r"^[A-Za-z0-9._~+/=-]{32,1024}$")
_OPAQUE_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$"
)
_ERROR_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,95}$")
_COMMAND_ID_PATTERN = re.compile(
    r"^cmd_[A-Za-z0-9][A-Za-z0-9._~-]{7,127}$"
)
_TRACE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID_PATTERN = re.compile(r"^[0-9a-f]{16}$")
_CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
_RETRYABLE_HTTP = frozenset({408, 425, 429, 500, 502, 503, 504})


class ProviderAuthorityError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class ProviderAuthorityConfigurationError(ProviderAuthorityError):
    def __init__(self, code: str) -> None:
        super().__init__(code, retryable=False)


class ProviderAuthorityContractError(ProviderAuthorityError):
    def __init__(self, code: str) -> None:
        super().__init__(code, retryable=False)


class ProviderAuthorityTransportError(ProviderAuthorityError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderAuthorityResponse:
    http_status: int
    response_hash: str
    value: dict[str, Any]


def _load_secret_file(name: str, *, code: str) -> str:
    file_name = os.getenv(name, "").strip()
    if not file_name or not os.path.isabs(file_name):
        raise ProviderAuthorityConfigurationError(code)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(file_name, flags)
    except OSError:
        raise ProviderAuthorityConfigurationError(code) from None
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in {0, os.geteuid()}
            or metadata.st_mode & 0o077
            or not 32 <= metadata.st_size <= 1024
        ):
            raise ProviderAuthorityConfigurationError(code)
        raw = os.read(descriptor, 1025)
        if len(raw) > 1024:
            raise ProviderAuthorityConfigurationError(code)
        try:
            secret = raw.decode("utf-8", "strict").strip()
        except UnicodeDecodeError:
            raise ProviderAuthorityConfigurationError(code) from None
    finally:
        os.close(descriptor)
    if not _SECRET_PATTERN.fullmatch(secret):
        raise ProviderAuthorityConfigurationError(code)
    return secret


def _is_loopback(hostname: str) -> bool:
    if hostname.lower().rstrip(".") == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def validate_provider_authority_url(value: str) -> str:
    if not value or value != value.strip() or any(
        character in value for character in "\r\n\t"
    ):
        raise ProviderAuthorityConfigurationError(
            "provider_authority_url_invalid"
        )
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ProviderAuthorityConfigurationError(
            "provider_authority_url_invalid"
        ) from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != PROVIDER_ENROLLMENT_AUTHORITY_PATH
        or parsed.query
        or parsed.fragment
        or (parsed.scheme == "http" and not _is_loopback(parsed.hostname))
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ProviderAuthorityConfigurationError(
            "provider_authority_url_invalid"
        )
    return value


@dataclass(frozen=True, slots=True)
class ProviderAuthoritySettings:
    command_url: str
    bearer_token: str = field(repr=False)
    identity_hmac_key: str = field(repr=False)
    signature_key_id: str = "key_provider_enrollment_v1"
    request_timeout_seconds: float = 10.0
    max_response_bytes: int = _MAX_RESPONSE_BYTES

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "command_url",
            validate_provider_authority_url(self.command_url),
        )
        if not _SECRET_PATTERN.fullmatch(self.bearer_token):
            raise ProviderAuthorityConfigurationError(
                "provider_authority_token_invalid"
            )
        if not _SECRET_PATTERN.fullmatch(self.identity_hmac_key):
            raise ProviderAuthorityConfigurationError(
                "provider_authority_identity_key_invalid"
            )
        if not _OPAQUE_ID_PATTERN.fullmatch(self.signature_key_id):
            raise ProviderAuthorityConfigurationError(
                "provider_authority_identity_key_id_invalid"
            )
        if not 0.25 <= self.request_timeout_seconds <= 60:
            raise ProviderAuthorityConfigurationError(
                "provider_authority_timeout_invalid"
            )
        if not 16 * 1024 <= self.max_response_bytes <= 512 * 1024:
            raise ProviderAuthorityConfigurationError(
                "provider_authority_response_limit_invalid"
            )

    @classmethod
    def from_env(cls) -> "ProviderAuthoritySettings":
        url = os.getenv("KOLIBRI_V3_PROVIDER_AUTHORITY_COMMAND_URL", "").strip()
        if not url:
            raise ProviderAuthorityConfigurationError(
                "provider_authority_url_missing"
            )
        try:
            timeout = float(
                os.getenv(
                    "KOLIBRI_V3_PROVIDER_AUTHORITY_REQUEST_TIMEOUT_SECONDS",
                    "10",
                )
            )
            limit = int(
                os.getenv(
                    "KOLIBRI_V3_PROVIDER_AUTHORITY_MAX_RESPONSE_BYTES",
                    str(_MAX_RESPONSE_BYTES),
                )
            )
        except ValueError:
            raise ProviderAuthorityConfigurationError(
                "provider_authority_limits_invalid"
            ) from None
        return cls(
            command_url=url,
            bearer_token=_load_secret_file(
                "KOLIBRI_V3_PROVIDER_AUTHORITY_COMMAND_TOKEN_FILE",
                code="provider_authority_token_invalid",
            ),
            identity_hmac_key=_load_secret_file(
                "KOLIBRI_V3_PROVIDER_AUTHORITY_IDENTITY_HMAC_KEY_FILE",
                code="provider_authority_identity_key_invalid",
            ),
            signature_key_id=os.getenv(
                "KOLIBRI_V3_PROVIDER_AUTHORITY_IDENTITY_KEY_ID",
                "key_provider_enrollment_v1",
            ).strip(),
            request_timeout_seconds=timeout,
            max_response_bytes=limit,
        )


def _strict_keys(
    value: Mapping[str, Any],
    expected: frozenset[str],
    *,
    code: str,
) -> None:
    if frozenset(value) != expected:
        raise ProviderAuthorityContractError(code)


def _require_opaque_id(value: Any, *, code: str) -> str:
    if not isinstance(value, str) or not _OPAQUE_ID_PATTERN.fullmatch(value):
        raise ProviderAuthorityContractError(code)
    return value


def _require_datetime(value: Any, *, code: str) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise ProviderAuthorityContractError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ProviderAuthorityContractError(code) from None
    if parsed.tzinfo is None:
        raise ProviderAuthorityContractError(code)
    return parsed


def decode_and_validate_command(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > _MAX_COMMAND_BYTES:
        raise ProviderAuthorityContractError(
            "provider_enrollment_command_invalid"
        )
    try:
        command = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ProviderAuthorityContractError(
            "provider_enrollment_command_invalid"
        ) from None
    if not isinstance(command, dict):
        raise ProviderAuthorityContractError(
            "provider_enrollment_command_invalid"
        )
    _strict_keys(
        command,
        frozenset(
            {
                "schema_id",
                "schema_version",
                "message_id",
                "command_name",
                "payload_schema_id",
                "payload_schema_version",
                "issued_at",
                "deadline_at",
                "target_owner",
                "identity",
                "trace",
                "idempotency",
                "payload",
            }
        ),
        code="provider_enrollment_command_invalid",
    )
    if (
        command.get("schema_id") != "kolibri.command"
        or command.get("schema_version") != "1.0"
        or command.get("command_name")
        != "product.provider.enrollment.request"
        or command.get("payload_schema_id")
        != "kolibri.product.provider.enrollment_intent.command"
        or command.get("payload_schema_version") != "1.0"
        or command.get("target_owner") != "provider_execution_authority"
        or not isinstance(command.get("message_id"), str)
        or not _COMMAND_ID_PATTERN.fullmatch(command["message_id"])
    ):
        raise ProviderAuthorityContractError(
            "provider_enrollment_command_invalid"
        )
    issued_at = _require_datetime(
        command.get("issued_at"),
        code="provider_enrollment_command_invalid",
    )
    deadline_at = _require_datetime(
        command.get("deadline_at"),
        code="provider_enrollment_command_invalid",
    )
    if deadline_at <= issued_at:
        raise ProviderAuthorityContractError(
            "provider_enrollment_command_invalid"
        )
    if deadline_at <= datetime.now(deadline_at.tzinfo):
        raise ProviderAuthorityContractError(
            "provider_enrollment_command_expired"
        )

    payload = command.get("payload")
    identity = command.get("identity")
    idempotency = command.get("idempotency")
    if not all(
        isinstance(value, dict)
        for value in (payload, identity, idempotency, command.get("trace"))
    ):
        raise ProviderAuthorityContractError(
            "provider_enrollment_command_invalid"
        )
    _strict_keys(
        payload,
        frozenset(
            {
                "schema_id",
                "schema_version",
                "tenant_id",
                "intent_id",
                "provider_id",
                "requested_by_user_id",
                "owner_authorization_decision_id",
                "purpose",
                "requested_at",
            }
        ),
        code="provider_enrollment_payload_invalid",
    )
    if (
        payload.get("schema_id")
        != "kolibri.product.provider.enrollment_intent.command"
        or payload.get("schema_version") != "1.0"
        or payload.get("provider_id") not in {"mimo-code", "codex-cli"}
        or payload.get("purpose") != "owner_provider_enrollment"
        or _require_datetime(
            payload.get("requested_at"),
            code="provider_enrollment_payload_invalid",
        )
        != issued_at
    ):
        raise ProviderAuthorityContractError(
            "provider_enrollment_payload_invalid"
        )
    for key in (
        "tenant_id",
        "intent_id",
        "requested_by_user_id",
        "owner_authorization_decision_id",
    ):
        _require_opaque_id(
            payload.get(key),
            code="provider_enrollment_payload_invalid",
        )

    _strict_keys(
        identity,
        frozenset(
            {"tenant_id", "user_id", "actor", "authority", "subject_refs"}
        ),
        code="provider_enrollment_identity_invalid",
    )
    actor = identity.get("actor")
    authority = identity.get("authority")
    subjects = identity.get("subject_refs")
    if not all(
        isinstance(value, dict) for value in (actor, authority, subjects)
    ):
        raise ProviderAuthorityContractError(
            "provider_enrollment_identity_invalid"
        )
    _strict_keys(
        actor,
        frozenset({"actor_id", "actor_type"}),
        code="provider_enrollment_identity_invalid",
    )
    _strict_keys(
        authority,
        frozenset(
            {
                "authority_id",
                "authority_role",
                "authority_epoch",
                "authority_placement_id",
                "authorization_decision_id",
                "capabilities",
            }
        ),
        code="provider_enrollment_identity_invalid",
    )
    _strict_keys(
        subjects,
        frozenset({"goal_id", "case_id", "task_id"}),
        code="provider_enrollment_identity_invalid",
    )
    for authority_id_key in (
        "authority_id",
        "authority_placement_id",
        "authorization_decision_id",
    ):
        _require_opaque_id(
            authority.get(authority_id_key),
            code="provider_enrollment_identity_invalid",
        )
    capabilities = authority.get("capabilities")
    if (
        identity.get("tenant_id") != payload["tenant_id"]
        or identity.get("user_id") != payload["requested_by_user_id"]
        or actor.get("actor_type") != "user"
        or not isinstance(actor.get("actor_id"), str)
        or not _OPAQUE_ID_PATTERN.fullmatch(actor["actor_id"])
        or authority.get("authority_role") != "product_data_authority"
        or not isinstance(authority.get("authority_epoch"), int)
        or isinstance(authority.get("authority_epoch"), bool)
        or authority["authority_epoch"] < 1
        or not isinstance(capabilities, list)
        or not capabilities
        or len(capabilities) != len(set(capabilities))
        or any(
            not isinstance(capability, str)
            or not _CAPABILITY_PATTERN.fullmatch(capability)
            for capability in capabilities
        )
        or "product.provider.enrollment.request"
        not in capabilities
        or subjects
        != {"goal_id": None, "case_id": None, "task_id": None}
    ):
        raise ProviderAuthorityContractError(
            "provider_enrollment_identity_invalid"
        )
    trace = command["trace"]
    _strict_keys(
        trace,
        frozenset(
            {
                "trace_id",
                "span_id",
                "parent_span_id",
                "correlation_id",
                "causation_id",
            }
        ),
        code="provider_enrollment_trace_invalid",
    )
    if (
        not isinstance(trace.get("trace_id"), str)
        or not _TRACE_ID_PATTERN.fullmatch(trace["trace_id"])
        or not isinstance(trace.get("span_id"), str)
        or not _SPAN_ID_PATTERN.fullmatch(trace["span_id"])
        or trace.get("parent_span_id") is not None
        or trace.get("correlation_id") != payload["intent_id"]
        or trace.get("causation_id") is not None
    ):
        raise ProviderAuthorityContractError(
            "provider_enrollment_trace_invalid"
        )
    _strict_keys(
        idempotency,
        frozenset(
            {"key", "scope", "scope_id", "canonical_request_hash"}
        ),
        code="provider_enrollment_idempotency_invalid",
    )
    if (
        idempotency.get("scope") != "aggregate"
        or idempotency.get("scope_id") != payload["intent_id"]
        or idempotency.get("key")
        != f"product.provider.enrollment:{payload['intent_id']}"
        or idempotency.get("canonical_request_hash")
        != canonical_command_hash(command)
    ):
        raise ProviderAuthorityContractError(
            "provider_enrollment_idempotency_invalid"
        )
    return command


def _identity_headers(
    secret: str,
    key_id: str,
    command: Mapping[str, Any],
    command_bytes: bytes,
) -> dict[str, str]:
    identity = command["identity"]
    actor = identity["actor"]
    timestamp = str(int(datetime.now().timestamp()))
    nonce = uuid.uuid4().hex
    body_hash = "sha256:" + hashlib.sha256(command_bytes).hexdigest()
    claims = {
        "method": "POST",
        "path": PROVIDER_ENROLLMENT_AUTHORITY_PATH,
        "body_sha256": body_hash,
        "idempotency_key": command["idempotency"]["key"],
        "timestamp": timestamp,
        "nonce": nonce,
        "signature_key_id": key_id,
        "message_id": command["message_id"],
        "tenant_id": identity["tenant_id"],
        "user_id": identity["user_id"],
        "actor": {
            "actor_id": actor["actor_id"],
            "actor_type": actor["actor_type"],
        },
        "authority": {
            "authority_id": identity["authority"]["authority_id"],
            "authority_epoch": identity["authority"]["authority_epoch"],
            "authorization_decision_id": identity["authority"][
                "authorization_decision_id"
            ],
        },
    }
    digest = hmac.new(
        secret.encode("utf-8", "strict"),
        json.dumps(
            claims,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", "strict"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-Kolibri-Tenant-Id": str(identity["tenant_id"]),
        "X-Kolibri-User-Id": str(identity["user_id"]),
        "X-Kolibri-Actor-Id": str(actor["actor_id"]),
        "X-Kolibri-Actor-Type": str(actor["actor_type"]),
        "X-Kolibri-Identity-Signature": f"sha256:{digest}",
        "X-Kolibri-Request-Timestamp": timestamp,
        "X-Kolibri-Request-Nonce": nonce,
        "X-Kolibri-Body-SHA256": body_hash,
        "X-Kolibri-Signature-Key-Id": key_id,
    }


def _validate_status(
    value: Any,
    *,
    command: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProviderAuthorityContractError(
            "provider_enrollment_status_invalid"
        )
    _strict_keys(
        value,
        frozenset(
            {
                "schema_id",
                "schema_version",
                "tenant_id",
                "intent_id",
                "provider_id",
                "status",
                "auth_flow_supported",
                "last_verified_at",
                "error",
            }
        ),
        code="provider_enrollment_status_invalid",
    )
    payload = command["payload"]
    status_value = value.get("status")
    last_verified_at = value.get("last_verified_at")
    error = value.get("error")
    if (
        value.get("schema_id")
        != "kolibri.product.provider.enrollment_status"
        or value.get("schema_version") != "1.0"
        or value.get("tenant_id") != payload["tenant_id"]
        or value.get("intent_id") != payload["intent_id"]
        or value.get("provider_id") != payload["provider_id"]
        or status_value
        not in {
            "connected",
            "failed",
        }
        or not isinstance(value.get("auth_flow_supported"), bool)
        or (
            last_verified_at is not None
            and not isinstance(last_verified_at, str)
        )
    ):
        raise ProviderAuthorityContractError(
            "provider_enrollment_status_invalid"
        )
    if isinstance(last_verified_at, str):
        _require_datetime(
            last_verified_at,
            code="provider_enrollment_status_invalid",
        )
    if status_value == "connected":
        if last_verified_at is None or error is not None:
            raise ProviderAuthorityContractError(
                "provider_enrollment_status_invalid"
            )
    elif status_value == "failed":
        if not isinstance(error, dict):
            raise ProviderAuthorityContractError(
                "provider_enrollment_status_invalid"
            )
        error_code = error.get("code")
        if (
            error.get("schema_id") != "kolibri.error"
            or error.get("schema_version") != "1.0"
            or error.get("in_response_to") != payload["intent_id"]
            or not isinstance(error_code, str)
            or not _ERROR_CODE_PATTERN.fullmatch(error_code)
        ):
            raise ProviderAuthorityContractError(
                "provider_enrollment_status_invalid"
            )
    elif error is not None:
        raise ProviderAuthorityContractError(
            "provider_enrollment_status_invalid"
        )
    return value


class ProviderAuthorityClient:
    def __init__(
        self,
        settings: ProviderAuthoritySettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    def submit(self, command_json: str | bytes) -> ProviderAuthorityResponse:
        command_bytes = (
            command_json.encode("utf-8", "strict")
            if isinstance(command_json, str)
            else command_json
        )
        command = decode_and_validate_command(command_bytes)
        headers = {
            "Authorization": f"Bearer {self.settings.bearer_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Idempotency-Key": str(command["idempotency"]["key"]),
            "X-Kolibri-Service-Scope": "provider-connections:enroll",
            **_identity_headers(
                self.settings.identity_hmac_key,
                self.settings.signature_key_id,
                command,
                command_bytes,
            ),
        }
        try:
            with httpx.Client(
                timeout=httpx.Timeout(
                    self.settings.request_timeout_seconds
                ),
                transport=self.transport,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                with client.stream(
                    "POST",
                    self.settings.command_url,
                    headers=headers,
                    content=command_bytes,
                ) as response:
                    if not 200 <= response.status_code < 300:
                        raise ProviderAuthorityTransportError(
                            f"provider_authority_http_{response.status_code}",
                            retryable=(
                                response.status_code in _RETRYABLE_HTTP
                            ),
                        )
                    media_type = response.headers.get(
                        "content-type", ""
                    ).split(";", 1)[0].strip().lower()
                    if media_type != "application/json":
                        raise ProviderAuthorityContractError(
                            "provider_authority_content_type_invalid"
                        )
                    declared = response.headers.get("content-length")
                    if declared is not None:
                        try:
                            if int(declared) > self.settings.max_response_bytes:
                                raise ProviderAuthorityContractError(
                                    "provider_authority_response_too_large"
                                )
                        except ValueError:
                            raise ProviderAuthorityContractError(
                                "provider_authority_response_length_invalid"
                            ) from None
                    chunks: list[bytes] = []
                    byte_count = 0
                    for chunk in response.iter_bytes():
                        byte_count += len(chunk)
                        if byte_count > self.settings.max_response_bytes:
                            raise ProviderAuthorityContractError(
                                "provider_authority_response_too_large"
                            )
                        chunks.append(chunk)
                    body = b"".join(chunks)
        except ProviderAuthorityError:
            raise
        except (httpx.HTTPError, OSError):
            raise ProviderAuthorityTransportError(
                "provider_authority_unavailable",
                retryable=True,
            ) from None
        if not body or len(body) > self.settings.max_response_bytes:
            raise ProviderAuthorityContractError(
                "provider_authority_response_too_large"
            )
        try:
            decoded = json.loads(body.decode("utf-8", "strict"))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise ProviderAuthorityContractError(
                "provider_enrollment_status_invalid"
            ) from None
        return ProviderAuthorityResponse(
            http_status=response.status_code,
            response_hash=(
                "sha256:" + hashlib.sha256(body).hexdigest()
            ),
            value=_validate_status(decoded, command=command),
        )


__all__ = [
    "PROVIDER_ENROLLMENT_AUTHORITY_PATH",
    "ProviderAuthorityClient",
    "ProviderAuthorityConfigurationError",
    "ProviderAuthorityContractError",
    "ProviderAuthorityError",
    "ProviderAuthorityResponse",
    "ProviderAuthoritySettings",
    "ProviderAuthorityTransportError",
    "decode_and_validate_command",
    "validate_provider_authority_url",
]
