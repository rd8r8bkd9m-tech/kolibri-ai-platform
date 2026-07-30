"""Strict Product/Data transport to the Logical Home Control Plane.

The Product worker stores one canonical command envelope in its outbox.  Every
delivery and poll sends those exact stored UTF-8 bytes to Logical Home; this
module never selects a physical provider node and never rebuilds the command.
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
from typing import Any, NoReturn
from urllib.parse import urlsplit, urlunsplit
import uuid

import httpx


PRODUCT_RUN_COMMAND_PATH = "/v1/runtime/product-text-runs"
PRODUCT_GOAL_INITIALIZATION_PATH = (
    "/v1/runtime/product-goal-initializations"
)
PRODUCT_PROVIDER_ENROLLMENT_PATH = (
    "/v1/runtime/product-provider-enrollment-intents"
)
_MAX_COMMAND_BYTES = 512 * 1024
_DEFAULT_MAX_RESPONSE_BYTES = 512 * 1024
_SECRET_PATTERN = re.compile(r"^[A-Za-z0-9._~+/=-]{32,1024}$")
_OPAQUE_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$"
)
_COMMAND_ID_PATTERN = re.compile(r"^cmd_[A-Za-z0-9][A-Za-z0-9._~-]{7,127}$")
_ERROR_ID_PATTERN = re.compile(r"^err_[A-Za-z0-9][A-Za-z0-9._~-]{7,127}$")
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_TRACE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID_PATTERN = re.compile(r"^[0-9a-f]{16}$")
_ERROR_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,95}$")
_CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
_SIGNATURE_KEY_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$"
)
_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:~-]+$")
_RUNTIME_PROFILE_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9._-]{1,95}$"
)
_MODEL_SELECTION_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$"
)
_RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
_PROFILES = frozenset({"mimo-code", "codex-cli"})
_RUN_STATES = frozenset({"accepted", "running", "succeeded", "failed"})
_VERIFICATION_STATES = frozenset(
    {"not_applicable", "unverified", "verified"}
)
_ERROR_CATEGORIES = frozenset(
    {
        "validation",
        "authentication",
        "authorization",
        "conflict",
        "not_found",
        "capacity",
        "dependency",
        "timeout",
        "internal",
    }
)


class HomeRuntimeError(RuntimeError):
    """A public-safe, classified Product-to-Home failure."""

    def __init__(
        self,
        code: str,
        *,
        retryable: bool,
        infrastructure_outage: bool = False,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.infrastructure_outage = infrastructure_outage


class HomeRuntimeConfigurationError(HomeRuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code, retryable=False)


class HomeRuntimeCommandError(HomeRuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code, retryable=False)


class HomeRuntimeTransportError(HomeRuntimeError):
    pass


class HomeRuntimeStatusError(HomeRuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code, retryable=False)


# Stable worker-facing names used by the V3 outbox process.
ProductRunExecutionError = HomeRuntimeError
ProductRunConfigurationError = HomeRuntimeConfigurationError
ProductRunCommandError = HomeRuntimeCommandError
ProductRunTransportError = HomeRuntimeTransportError
ProductRunStatusError = HomeRuntimeStatusError


@dataclass(frozen=True, slots=True)
class HomeRuntimeResponse:
    """Validated Home response plus the exact UTF-8 body for the audit ledger."""

    http_status: int
    body_text: str
    value: dict[str, Any]


def _load_runtime_secret(name: str, *, error_code: str) -> str:
    """Load exactly one direct secret or locked-down systemd credential file."""

    direct = os.getenv(name, "").strip()
    file_name = os.getenv(f"{name}_FILE", "").strip()
    if bool(direct) == bool(file_name):
        raise HomeRuntimeConfigurationError(error_code)
    if direct:
        value = direct
    else:
        if not os.path.isabs(file_name):
            raise HomeRuntimeConfigurationError(error_code)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(file_name, flags)
        except OSError:
            raise HomeRuntimeConfigurationError(error_code) from None
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid not in {0, os.geteuid()}
                or metadata.st_mode & 0o077
                or not 32 <= metadata.st_size <= 1024
            ):
                raise HomeRuntimeConfigurationError(error_code)
            raw = os.read(descriptor, 1025)
            if len(raw) > 1024:
                raise HomeRuntimeConfigurationError(error_code)
            try:
                value = raw.decode("utf-8", "strict").strip()
            except UnicodeDecodeError:
                raise HomeRuntimeConfigurationError(error_code) from None
        finally:
            os.close(descriptor)
    if not _SECRET_PATTERN.fullmatch(value):
        raise HomeRuntimeConfigurationError(error_code)
    return value


def validate_home_product_command_url(value: str) -> str:
    """Accept HTTPS, or HTTP only when the destination itself is loopback."""

    return _validate_home_product_url(value, PRODUCT_RUN_COMMAND_PATH)


def validate_home_product_goal_url(value: str) -> str:
    """Validate the Product-authenticated Goal initialization endpoint."""

    return _validate_home_product_url(
        value,
        PRODUCT_GOAL_INITIALIZATION_PATH,
    )


def validate_home_product_provider_url(value: str) -> str:
    """Validate the Product-authenticated provider-check endpoint."""

    return _validate_home_product_url(
        value,
        PRODUCT_PROVIDER_ENROLLMENT_PATH,
    )


def _validate_home_product_url(value: str, expected_path: str) -> str:
    candidate = value.strip()
    if not candidate or candidate != value or any(
        character in candidate for character in "\r\n\t"
    ):
        raise HomeRuntimeConfigurationError(
            "home_product_command_url_invalid"
        )
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        raise HomeRuntimeConfigurationError(
            "home_product_command_url_invalid"
        ) from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != expected_path
        or parsed.query
        or parsed.fragment
    ):
        raise HomeRuntimeConfigurationError(
            "home_product_command_url_invalid"
        )
    hostname = parsed.hostname
    if parsed.scheme == "http" and not _is_loopback_hostname(hostname):
        raise HomeRuntimeConfigurationError(
            "home_product_command_url_invalid"
        )
    if port is not None and not 1 <= port <= 65535:
        raise HomeRuntimeConfigurationError(
            "home_product_command_url_invalid"
        )
    return candidate


def _is_loopback_hostname(hostname: str) -> bool:
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class HomeRuntimeSettings:
    """Worker-only Logical Home transport configuration."""

    command_url: str
    bearer_token: str = field(repr=False)
    identity_hmac_key: str = field(repr=False)
    identity_hmac_key_id: str = "key_product_v3_v1"
    goal_command_url: str | None = None
    provider_enrollment_command_url: str | None = None
    request_timeout_seconds: float = 10.0
    max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES
    lease_seconds: float = 30.0
    poll_seconds: float = 0.5
    retry_base_seconds: float = 1.0
    idle_seconds: float = 0.25

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "command_url",
            validate_home_product_command_url(self.command_url),
        )
        goal_command_url = self.goal_command_url
        if goal_command_url is None:
            parsed = urlsplit(self.command_url)
            goal_command_url = urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc,
                    PRODUCT_GOAL_INITIALIZATION_PATH,
                    "",
                    "",
                )
            )
        validated_goal_url = validate_home_product_goal_url(
            goal_command_url
        )
        if _url_origin(self.command_url) != _url_origin(validated_goal_url):
            raise HomeRuntimeConfigurationError(
                "home_product_goal_command_origin_invalid"
            )
        object.__setattr__(
            self,
            "goal_command_url",
            validated_goal_url,
        )
        provider_command_url = self.provider_enrollment_command_url
        if provider_command_url is None:
            parsed = urlsplit(self.command_url)
            provider_command_url = urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc,
                    PRODUCT_PROVIDER_ENROLLMENT_PATH,
                    "",
                    "",
                )
            )
        validated_provider_url = validate_home_product_provider_url(
            provider_command_url
        )
        if _url_origin(self.command_url) != _url_origin(
            validated_provider_url
        ):
            raise HomeRuntimeConfigurationError(
                "home_product_provider_command_origin_invalid"
            )
        object.__setattr__(
            self,
            "provider_enrollment_command_url",
            validated_provider_url,
        )
        if not _SECRET_PATTERN.fullmatch(self.bearer_token):
            raise HomeRuntimeConfigurationError(
                "home_product_command_token_invalid"
            )
        if not _SECRET_PATTERN.fullmatch(self.identity_hmac_key):
            raise HomeRuntimeConfigurationError(
                "home_product_identity_key_invalid"
            )
        if not _SIGNATURE_KEY_ID_PATTERN.fullmatch(
            self.identity_hmac_key_id
        ):
            raise HomeRuntimeConfigurationError(
                "home_product_identity_key_id_invalid"
            )
        if not 0.25 <= self.request_timeout_seconds <= 60:
            raise HomeRuntimeConfigurationError(
                "home_product_request_timeout_invalid"
            )
        if not (
            5 <= self.lease_seconds <= 300
            and self.lease_seconds >= self.request_timeout_seconds + 1
            and 0.05 <= self.poll_seconds <= 30
            and 0.1 <= self.retry_base_seconds <= 60
            and 0.05 <= self.idle_seconds <= 30
        ):
            raise HomeRuntimeConfigurationError(
                "home_product_worker_timing_invalid"
            )
        if not 16 * 1024 <= self.max_response_bytes <= 2 * 1024 * 1024:
            raise HomeRuntimeConfigurationError(
                "home_product_response_limit_invalid"
            )

    @classmethod
    def from_env(cls) -> "HomeRuntimeSettings":
        command_url = os.getenv(
            "KOLIBRI_V3_HOME_PRODUCT_COMMAND_URL", ""
        ).strip()
        if not command_url:
            raise HomeRuntimeConfigurationError(
                "home_product_command_url_missing"
            )
        bearer_token = _load_runtime_secret(
            "KOLIBRI_V3_HOME_PRODUCT_COMMAND_TOKEN",
            error_code="home_product_command_token_invalid",
        )
        identity_hmac_key = _load_runtime_secret(
            "KOLIBRI_V3_HOME_PRODUCT_IDENTITY_HMAC_KEY",
            error_code="home_product_identity_key_invalid",
        )
        try:
            timeout = float(
                os.getenv(
                    "KOLIBRI_V3_HOME_PRODUCT_REQUEST_TIMEOUT_SECONDS", "10"
                )
            )
            response_limit = int(
                os.getenv(
                    "KOLIBRI_V3_HOME_PRODUCT_MAX_RESPONSE_BYTES",
                    str(_DEFAULT_MAX_RESPONSE_BYTES),
                )
            )
            lease_seconds = float(
                os.getenv("KOLIBRI_V3_PRODUCT_RUN_LEASE_SECONDS", "30")
            )
            poll_seconds = float(
                os.getenv("KOLIBRI_V3_PRODUCT_RUN_POLL_SECONDS", "0.5")
            )
            retry_base_seconds = float(
                os.getenv(
                    "KOLIBRI_V3_PRODUCT_RUN_RETRY_BASE_SECONDS", "1"
                )
            )
            idle_seconds = float(
                os.getenv("KOLIBRI_V3_PRODUCT_RUN_IDLE_SECONDS", "0.25")
            )
        except ValueError:
            raise HomeRuntimeConfigurationError(
                "home_product_transport_limits_invalid"
            ) from None
        return cls(
            command_url=command_url,
            bearer_token=bearer_token,
            identity_hmac_key=identity_hmac_key,
            identity_hmac_key_id=os.getenv(
                "KOLIBRI_V3_HOME_PRODUCT_IDENTITY_KEY_ID",
                "key_product_v3_v1",
            ).strip(),
            goal_command_url=(
                os.getenv(
                    "KOLIBRI_V3_HOME_PRODUCT_GOAL_COMMAND_URL", ""
                ).strip()
                or None
            ),
            provider_enrollment_command_url=(
                os.getenv(
                    "KOLIBRI_V3_HOME_PRODUCT_PROVIDER_COMMAND_URL", ""
                ).strip()
                or None
            ),
            request_timeout_seconds=timeout,
            max_response_bytes=response_limit,
            lease_seconds=lease_seconds,
            poll_seconds=poll_seconds,
            retry_base_seconds=retry_base_seconds,
            idle_seconds=idle_seconds,
        )


ProductRunExecutionSettings = HomeRuntimeSettings


def _url_origin(value: str) -> tuple[str, str, int]:
    parsed = urlsplit(value)
    default_port = 443 if parsed.scheme == "https" else 80
    return (
        parsed.scheme,
        str(parsed.hostname).lower(),
        parsed.port or default_port,
    )


def _strict_keys(
    value: Mapping[str, Any],
    expected: frozenset[str],
    *,
    code: str,
) -> None:
    if frozenset(value) != expected:
        raise HomeRuntimeCommandError(code)


class _DuplicateJsonKey(ValueError):
    pass


def _object_without_duplicates(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _reject_json_constant(_: str) -> Any:
    raise ValueError("non-finite JSON number")


def _decode_json_object(
    raw: bytes,
    *,
    invalid_code: str,
) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        raise HomeRuntimeCommandError(invalid_code) from None
    if not isinstance(value, dict):
        raise HomeRuntimeCommandError(invalid_code)
    return value


def _stored_command_bytes(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        try:
            raw = value.encode("utf-8", "strict")
        except UnicodeEncodeError:
            raise HomeRuntimeCommandError(
                "home_product_command_encoding_invalid"
            ) from None
    else:
        raise HomeRuntimeCommandError("home_product_command_encoding_invalid")
    if not raw or len(raw) > _MAX_COMMAND_BYTES:
        raise HomeRuntimeCommandError("home_product_command_size_invalid")
    return raw


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_string(
    value: Any,
    *,
    code: str,
    minimum: int = 1,
    maximum: int,
    pattern: re.Pattern[str] | None = None,
) -> str:
    if (
        not isinstance(value, str)
        or not minimum <= len(value) <= maximum
        or (pattern is not None and not pattern.fullmatch(value))
    ):
        raise HomeRuntimeCommandError(code)
    return value


def _require_opaque_id(value: Any, *, code: str) -> str:
    return _require_string(
        value,
        code=code,
        maximum=160,
        pattern=_OPAQUE_ID_PATTERN,
    )


def _require_datetime(value: Any, *, code: str) -> datetime:
    if not isinstance(value, str):
        raise HomeRuntimeCommandError(code)
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        raise HomeRuntimeCommandError(code) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HomeRuntimeCommandError(code)
    return parsed


def _sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8', 'strict')).hexdigest()}"


def _canonical_hash(value: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise HomeRuntimeCommandError(
            "home_product_canonical_request_invalid"
        ) from None
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def parse_stored_product_command(value: str | bytes) -> tuple[bytes, dict[str, Any]]:
    """Parse and validate a stored command without changing its wire bytes."""

    raw = _stored_command_bytes(value)
    command = _decode_json_object(
        raw,
        invalid_code="home_product_command_json_invalid",
    )
    _validate_product_command(command)
    return raw, command


def parse_stored_goal_command(value: str | bytes) -> tuple[bytes, dict[str, Any]]:
    """Parse a stored Goal initialization command without rewriting it."""

    raw = _stored_command_bytes(value)
    command = _decode_json_object(
        raw,
        invalid_code="home_product_goal_command_json_invalid",
    )
    _validate_goal_command(command)
    return raw, command


def _validate_product_command(command: dict[str, Any]) -> None:
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
        code="home_product_command_contract_invalid",
    )
    payload_contract = (
        command.get("payload_schema_id"),
        command.get("payload_schema_version"),
    )
    if (
        command.get("schema_id") != "kolibri.command"
        or command.get("schema_version") != "1.0"
        or command.get("command_name") != "product.run.execute"
        or payload_contract
        not in {
            ("kolibri.product.run.execute.command", "1.0"),
            ("kolibri.product.run.execute.v1_1.command", "1.1"),
            ("kolibri.product.run.execute.v1_2.command", "1.2"),
            ("kolibri.product.run.execute.v1_3.command", "1.3"),
        }
        or command.get("target_owner") != "logical_home_control_plane"
    ):
        raise HomeRuntimeCommandError(
            "home_product_command_contract_invalid"
        )
    _require_string(
        command.get("message_id"),
        code="home_product_command_contract_invalid",
        maximum=132,
        pattern=_COMMAND_ID_PATTERN,
    )
    issued_at = _require_datetime(
        command.get("issued_at"),
        code="home_product_command_contract_invalid",
    )
    deadline_at = _require_datetime(
        command.get("deadline_at"),
        code="home_product_command_contract_invalid",
    )
    if deadline_at <= issued_at:
        raise HomeRuntimeCommandError(
            "home_product_command_contract_invalid"
        )

    payload = command.get("payload")
    identity = command.get("identity")
    trace = command.get("trace")
    idempotency = command.get("idempotency")
    if not all(
        isinstance(item, dict)
        for item in (payload, identity, trace, idempotency)
    ):
        raise HomeRuntimeCommandError(
            "home_product_command_contract_invalid"
        )
    _validate_product_payload(payload)
    if (
        payload.get("schema_id"),
        payload.get("schema_version"),
    ) != payload_contract:
        raise HomeRuntimeCommandError(
            "home_product_command_contract_invalid"
        )
    _validate_product_identity(
        identity,
        payload,
        required_capability=(
            "product.developer.run.execute.request"
            if payload_contract
            in {
                ("kolibri.product.run.execute.v1_2.command", "1.2"),
                ("kolibri.product.run.execute.v1_3.command", "1.3"),
            }
            else "product.run.execute.request"
        ),
        expected_case_id=payload["case_id"],
    )
    _validate_trace(trace, payload)
    _validate_idempotency(
        idempotency,
        command,
        identity,
        payload,
        expected_key=f"product.run.execute:{payload['run_id']}",
        expected_scope="aggregate",
        expected_scope_id=payload["run_id"],
    )


def _validate_product_payload(payload: dict[str, Any]) -> None:
    payload_contract = (
        payload.get("schema_id"),
        payload.get("schema_version"),
    )
    is_v1_1 = payload_contract == (
        "kolibri.product.run.execute.v1_1.command",
        "1.1",
    )
    is_v1_2 = payload_contract == (
        "kolibri.product.run.execute.v1_2.command",
        "1.2",
    )
    is_v1_3 = payload_contract == (
        "kolibri.product.run.execute.v1_3.command",
        "1.3",
    )
    if payload_contract not in {
        ("kolibri.product.run.execute.command", "1.0"),
        ("kolibri.product.run.execute.v1_1.command", "1.1"),
        ("kolibri.product.run.execute.v1_2.command", "1.2"),
        ("kolibri.product.run.execute.v1_3.command", "1.3"),
    }:
        raise HomeRuntimeCommandError(
            "home_product_command_payload_invalid"
        )
    common_keys = {
        "schema_id",
        "schema_version",
        "tenant_id",
        "project_id",
        "thread_id",
        "run_id",
        "input_message_id",
        "case_id",
        "goal_id",
        "prompt",
        "prompt_hash",
    }
    version_keys = (
        {
            "execution_mode",
            "runtime_profile",
            "model",
            "reasoning_effort",
            "service_tier",
            "workspace_ref",
            "access_mode",
            "sandbox",
            "approval_policy",
            "reviewer",
            "requester_role",
        }
        | (
            {
                "trusted_agent_profile_id",
                "trusted_agent_profile_epoch",
                "trusted_agent_workspace_binding_id",
                "trusted_agent_workspace_binding_epoch",
            }
            if is_v1_3
            else set()
        )
        if is_v1_2 or is_v1_3
        else {
            "preferred_agent_profile",
            *(
                {
                    "preferred_model",
                    "preferred_reasoning_effort",
                }
                if is_v1_1
                else set()
            ),
        }
    )
    _strict_keys(
        payload,
        frozenset(common_keys | version_keys),
        code="home_product_command_payload_invalid",
    )
    for field_name in (
        "tenant_id",
        "project_id",
        "thread_id",
        "run_id",
        "input_message_id",
        "case_id",
        "goal_id",
    ):
        _require_opaque_id(
            payload.get(field_name),
            code="home_product_command_payload_invalid",
        )
    prompt = _require_string(
        payload.get("prompt"),
        code="home_product_command_payload_invalid",
        maximum=200_000,
    )
    prompt_hash = payload.get("prompt_hash")
    if (
        not isinstance(prompt_hash, str)
        or not _SHA256_PATTERN.fullmatch(prompt_hash)
        or prompt_hash != _sha256_text(prompt)
    ):
        raise HomeRuntimeCommandError(
            "home_product_command_payload_invalid"
        )
    if is_v1_2 or is_v1_3:
        _require_string(
            payload.get("runtime_profile"),
            code="home_product_command_payload_invalid",
            minimum=2,
            maximum=96,
            pattern=_RUNTIME_PROFILE_PATTERN,
        )
        for field_name, maximum, pattern in (
            (
                "model",
                120,
                _MODEL_SELECTION_PATTERN,
            ),
            (
                "reasoning_effort",
                32,
                re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$"),
            ),
            (
                "service_tier",
                32,
                re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$"),
            ),
            (
                "reviewer",
                120,
                _MODEL_SELECTION_PATTERN,
            ),
        ):
            option = payload[field_name]
            if option is not None:
                _require_string(
                    option,
                    code="home_product_command_payload_invalid",
                    maximum=maximum,
                    pattern=pattern,
                )
        _require_string(
            payload.get("workspace_ref"),
            code="home_product_command_payload_invalid",
            maximum=160,
            pattern=re.compile(
                r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$"
            ),
        )
        if (
            payload.get("execution_mode") != "developer"
            or payload.get("requester_role") != "owner"
            or payload.get("access_mode") not in {"auto", "full"}
            or payload.get("sandbox")
            not in {"workspace-write", "danger-full-access"}
            or payload.get("approval_policy")
            not in {"on-request", "never"}
        ):
            raise HomeRuntimeCommandError(
                "home_product_command_payload_invalid"
            )
        if is_v1_3:
            if (
                payload.get("runtime_profile") == "auto"
                or payload.get("access_mode") != "full"
                or payload.get("sandbox") != "danger-full-access"
                or payload.get("approval_policy") != "never"
                or payload.get("reviewer") is not None
            ):
                raise HomeRuntimeCommandError(
                    "home_product_command_payload_invalid"
                )
            for field_name, pattern in (
                (
                    "trusted_agent_profile_id",
                    re.compile(r"^tap_[0-9a-f]{32}$"),
                ),
                (
                    "trusted_agent_workspace_binding_id",
                    re.compile(r"^wsb_[0-9a-f]{32}$"),
                ),
            ):
                _require_string(
                    payload.get(field_name),
                    code="home_product_command_payload_invalid",
                    maximum=36,
                    pattern=pattern,
                )
            for field_name in (
                "trusted_agent_profile_epoch",
                "trusted_agent_workspace_binding_epoch",
            ):
                epoch = payload.get(field_name)
                if (
                    isinstance(epoch, bool)
                    or not isinstance(epoch, int)
                    or epoch < 1
                    or epoch > 9_007_199_254_740_991
                ):
                    raise HomeRuntimeCommandError(
                        "home_product_command_payload_invalid"
                    )
        return
    profile = payload.get("preferred_agent_profile")
    if (
        not isinstance(profile, str)
        or _RUNTIME_PROFILE_PATTERN.fullmatch(profile) is None
    ):
        raise HomeRuntimeCommandError(
            "home_product_command_payload_invalid"
        )
    if is_v1_1:
        model = payload["preferred_model"]
        effort = payload["preferred_reasoning_effort"]
        if (model is None) != (effort is None):
            raise HomeRuntimeCommandError(
                "home_product_command_payload_invalid"
            )
        if model is not None:
            _require_string(
                model,
                code="home_product_command_payload_invalid",
                maximum=120,
                pattern=re.compile(
                    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$"
                ),
            )
        if effort is not None:
            _require_string(
                effort,
                code="home_product_command_payload_invalid",
                maximum=32,
                pattern=re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$"),
            )


def _validate_goal_command(command: dict[str, Any]) -> None:
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
        code="home_product_goal_command_contract_invalid",
    )
    if (
        command.get("schema_id") != "kolibri.command"
        or command.get("schema_version") != "1.0"
        or command.get("command_name") != "product.goal.initialize"
        or command.get("payload_schema_id")
        != "kolibri.product.goal.initialize.command"
        or command.get("payload_schema_version") != "1.0"
        or command.get("target_owner") != "logical_home_control_plane"
    ):
        raise HomeRuntimeCommandError(
            "home_product_goal_command_contract_invalid"
        )
    _require_string(
        command.get("message_id"),
        code="home_product_goal_command_contract_invalid",
        maximum=132,
        pattern=_COMMAND_ID_PATTERN,
    )
    issued_at = _require_datetime(
        command.get("issued_at"),
        code="home_product_goal_command_contract_invalid",
    )
    deadline_at = _require_datetime(
        command.get("deadline_at"),
        code="home_product_goal_command_contract_invalid",
    )
    if deadline_at <= issued_at:
        raise HomeRuntimeCommandError(
            "home_product_goal_command_contract_invalid"
        )
    payload = command.get("payload")
    identity = command.get("identity")
    trace = command.get("trace")
    idempotency = command.get("idempotency")
    if not all(
        isinstance(item, dict)
        for item in (payload, identity, trace, idempotency)
    ):
        raise HomeRuntimeCommandError(
            "home_product_goal_command_contract_invalid"
        )
    _validate_goal_payload(payload)
    _validate_product_identity(
        identity,
        payload,
        required_capability="product.goal.initialize.request",
        expected_case_id=None,
    )
    _validate_trace(trace, payload)
    _validate_idempotency(
        idempotency,
        command,
        identity,
        payload,
        expected_key=f"product.goal.initialize:{payload['goal_id']}",
        expected_scope="goal",
        expected_scope_id=payload["goal_id"],
    )


def _validate_goal_payload(payload: dict[str, Any]) -> None:
    _strict_keys(
        payload,
        frozenset(
            {
                "schema_id",
                "schema_version",
                "tenant_id",
                "project_id",
                "thread_id",
                "run_id",
                "input_message_id",
                "goal_id",
                "prompt",
                "prompt_hash",
            }
        ),
        code="home_product_goal_command_payload_invalid",
    )
    if (
        payload.get("schema_id")
        != "kolibri.product.goal.initialize.command"
        or payload.get("schema_version") != "1.0"
    ):
        raise HomeRuntimeCommandError(
            "home_product_goal_command_payload_invalid"
        )
    for field_name in (
        "tenant_id",
        "project_id",
        "thread_id",
        "run_id",
        "input_message_id",
        "goal_id",
    ):
        _require_opaque_id(
            payload.get(field_name),
            code="home_product_goal_command_payload_invalid",
        )
    prompt = _require_string(
        payload.get("prompt"),
        code="home_product_goal_command_payload_invalid",
        maximum=20_000,
    )
    prompt_hash = payload.get("prompt_hash")
    if (
        not isinstance(prompt_hash, str)
        or not _SHA256_PATTERN.fullmatch(prompt_hash)
        or prompt_hash != _sha256_text(prompt)
    ):
        raise HomeRuntimeCommandError(
            "home_product_goal_command_payload_invalid"
        )


def _validate_product_identity(
    identity: dict[str, Any],
    payload: dict[str, Any],
    *,
    required_capability: str,
    expected_case_id: str | None,
) -> None:
    _strict_keys(
        identity,
        frozenset(
            {"tenant_id", "user_id", "actor", "authority", "subject_refs"}
        ),
        code="home_product_command_identity_invalid",
    )
    tenant_id = _require_opaque_id(
        identity.get("tenant_id"),
        code="home_product_command_identity_invalid",
    )
    user_id_value = identity.get("user_id")
    user_id = (
        None
        if user_id_value is None
        else _require_opaque_id(
            user_id_value,
            code="home_product_command_identity_invalid",
        )
    )
    if tenant_id != payload["tenant_id"]:
        raise HomeRuntimeCommandError(
            "home_product_command_identity_invalid"
        )

    actor = identity.get("actor")
    authority = identity.get("authority")
    subjects = identity.get("subject_refs")
    if not all(isinstance(item, dict) for item in (actor, authority, subjects)):
        raise HomeRuntimeCommandError(
            "home_product_command_identity_invalid"
        )
    _strict_keys(
        actor,
        frozenset({"actor_id", "actor_type"}),
        code="home_product_command_identity_invalid",
    )
    _require_opaque_id(
        actor.get("actor_id"),
        code="home_product_command_identity_invalid",
    )
    actor_type = actor.get("actor_type")
    if actor_type not in {"user", "service", "agent", "system"} or (
        user_id is None and actor_type != "system"
    ):
        raise HomeRuntimeCommandError(
            "home_product_command_identity_invalid"
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
        code="home_product_command_authority_invalid",
    )
    for field_name in (
        "authority_id",
        "authority_placement_id",
        "authorization_decision_id",
    ):
        _require_opaque_id(
            authority.get(field_name),
            code="home_product_command_authority_invalid",
        )
    capabilities = authority.get("capabilities")
    if (
        authority.get("authority_role") != "product_data_authority"
        or not _is_int(authority.get("authority_epoch"))
        or authority["authority_epoch"] < 1
        or not isinstance(capabilities, list)
        or not capabilities
        or any(
            not isinstance(item, str)
            or not _CAPABILITY_PATTERN.fullmatch(item)
            for item in capabilities
        )
        or len(capabilities) != len(set(capabilities))
        or required_capability not in capabilities
    ):
        raise HomeRuntimeCommandError(
            "home_product_command_authority_invalid"
        )

    _strict_keys(
        subjects,
        frozenset({"goal_id", "case_id", "task_id"}),
        code="home_product_command_identity_invalid",
    )
    if (
        subjects.get("goal_id") != payload["goal_id"]
        or subjects.get("case_id") != expected_case_id
        or subjects.get("task_id") is not None
    ):
        raise HomeRuntimeCommandError(
            "home_product_command_identity_invalid"
        )


def _validate_trace(trace: dict[str, Any], payload: dict[str, Any]) -> None:
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
        code="home_product_command_trace_invalid",
    )
    if (
        not isinstance(trace.get("trace_id"), str)
        or not _TRACE_ID_PATTERN.fullmatch(trace["trace_id"])
        or not isinstance(trace.get("span_id"), str)
        or not _SPAN_ID_PATTERN.fullmatch(trace["span_id"])
        or (
            trace.get("parent_span_id") is not None
            and (
                not isinstance(trace["parent_span_id"], str)
                or not _SPAN_ID_PATTERN.fullmatch(trace["parent_span_id"])
            )
        )
        or trace.get("correlation_id") != payload["run_id"]
        or trace.get("causation_id") != payload["input_message_id"]
    ):
        raise HomeRuntimeCommandError(
            "home_product_command_trace_invalid"
        )


def _validate_idempotency(
    idempotency: dict[str, Any],
    command: dict[str, Any],
    identity: dict[str, Any],
    payload: dict[str, Any],
    *,
    expected_key: str,
    expected_scope: str,
    expected_scope_id: str,
) -> None:
    _strict_keys(
        idempotency,
        frozenset(
            {"key", "scope", "scope_id", "canonical_request_hash"}
        ),
        code="home_product_command_idempotency_invalid",
    )
    key = idempotency.get("key")
    if (
        not isinstance(key, str)
        or not 16 <= len(key) <= 200
        or not _IDEMPOTENCY_KEY_PATTERN.fullmatch(key)
        or key != expected_key
        or idempotency.get("scope") != expected_scope
        or idempotency.get("scope_id") != expected_scope_id
    ):
        raise HomeRuntimeCommandError(
            "home_product_command_idempotency_invalid"
        )
    effect = {
        "schema_id": command["schema_id"],
        "schema_version": command["schema_version"],
        "command_name": command["command_name"],
        "payload_schema_id": command["payload_schema_id"],
        "payload_schema_version": command["payload_schema_version"],
        "target_owner": command["target_owner"],
        "tenant_id": identity["tenant_id"],
        "user_id": identity["user_id"],
        "actor": identity["actor"],
        "subject_refs": identity["subject_refs"],
        "idempotency_scope": idempotency["scope"],
        "idempotency_scope_id": idempotency["scope_id"],
        "payload": payload,
    }
    if idempotency.get("canonical_request_hash") != _canonical_hash(effect):
        raise HomeRuntimeCommandError(
            "home_product_canonical_request_hash_invalid"
        )


def product_identity_headers(
    secret: str,
    key_id: str,
    command: Mapping[str, Any],
    command_bytes: bytes,
    *,
    method: str,
    logical_path: str,
) -> dict[str, str]:
    """Build the exact identity proof expected by the Logical Home gateway."""

    identity = command.get("identity")
    if not isinstance(identity, Mapping):
        raise HomeRuntimeCommandError(
            "home_product_command_identity_invalid"
        )
    actor = identity.get("actor")
    if not isinstance(actor, Mapping):
        raise HomeRuntimeCommandError(
            "home_product_command_identity_invalid"
        )
    authority = identity.get("authority")
    idempotency = command.get("idempotency")
    if not isinstance(authority, Mapping) or not isinstance(
        idempotency,
        Mapping,
    ):
        raise HomeRuntimeCommandError(
            "home_product_command_identity_invalid"
        )
    if (
        os.getenv("KOLIBRI_V3_HOME_PRODUCT_IDENTITY_PROOF_VERSION", "2")
        .strip()
        == "1"
    ):
        claims = {
            "message_id": command.get("message_id"),
            "tenant_id": identity.get("tenant_id"),
            "user_id": identity.get("user_id"),
            "actor": {
                "actor_id": actor.get("actor_id"),
                "actor_type": actor.get("actor_type"),
            },
        }
        digest = hmac.new(
            secret.encode("utf-8", "strict"),
            json.dumps(
                claims,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8", "strict"),
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "X-Kolibri-Tenant-Id": str(identity["tenant_id"]),
            "X-Kolibri-Actor-Id": str(actor["actor_id"]),
            "X-Kolibri-Actor-Type": str(actor["actor_type"]),
            "X-Kolibri-Identity-Signature": f"sha256:{digest}",
        }
        if identity["user_id"] is not None:
            headers["X-Kolibri-User-Id"] = str(identity["user_id"])
        return headers
    timestamp = str(int(datetime.now().timestamp()))
    nonce = uuid.uuid4().hex
    body_hash = (
        "sha256:" + hashlib.sha256(command_bytes).hexdigest()
    )
    claims = {
        "identity_proof_version": "2.0",
        "method": method,
        "path": logical_path,
        "body_sha256": body_hash,
        "idempotency_key": idempotency.get("key"),
        "timestamp": timestamp,
        "nonce": nonce,
        "signature_key_id": key_id,
        "message_id": command.get("message_id"),
        "tenant_id": identity.get("tenant_id"),
        "user_id": identity.get("user_id"),
        "actor": {
            "actor_id": actor.get("actor_id"),
            "actor_type": actor.get("actor_type"),
        },
        "authority": dict(authority),
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
    headers = {
        "X-Kolibri-Tenant-Id": str(identity["tenant_id"]),
        "X-Kolibri-Actor-Id": str(actor["actor_id"]),
        "X-Kolibri-Actor-Type": str(actor["actor_type"]),
        "X-Kolibri-Identity-Signature": f"sha256:{digest}",
        "X-Kolibri-Identity-Proof-Version": "2.0",
        "X-Kolibri-Request-Timestamp": timestamp,
        "X-Kolibri-Request-Nonce": nonce,
        "X-Kolibri-Body-SHA256": body_hash,
        "X-Kolibri-Signature-Key-Id": key_id,
    }
    if identity["user_id"] is not None:
        headers["X-Kolibri-User-Id"] = str(identity["user_id"])
    return headers


def _status_error(code: str) -> NoReturn:
    raise HomeRuntimeStatusError(code)


def _status_str(
    value: Any,
    *,
    code: str,
    minimum: int = 1,
    maximum: int,
    pattern: re.Pattern[str] | None = None,
) -> str:
    try:
        return _require_string(
            value,
            code=code,
            minimum=minimum,
            maximum=maximum,
            pattern=pattern,
        )
    except HomeRuntimeCommandError:
        _status_error(code)


def validate_product_execution_status(
    value: Mapping[str, Any],
    command: Mapping[str, Any],
    *,
    expected_execution_id: str | None = None,
    expected_profile: str | None = None,
) -> dict[str, Any]:
    """Validate the complete status contract and its durable run bindings."""

    if not isinstance(value, dict):
        _status_error("home_product_status_contract_invalid")
    payload = command.get("payload")
    if not isinstance(payload, Mapping):
        _status_error("home_product_status_run_binding_invalid")
    standard_selection_command = (
        command.get("payload_schema_id")
        == "kolibri.product.run.execute.v1_1.command"
        and command.get("payload_schema_version") == "1.1"
        and payload.get("schema_id")
        == "kolibri.product.run.execute.v1_1.command"
        and payload.get("schema_version") == "1.1"
    )
    developer_command = (
        (
            command.get("payload_schema_id"),
            command.get("payload_schema_version"),
        )
        in {
            ("kolibri.product.run.execute.v1_2.command", "1.2"),
            ("kolibri.product.run.execute.v1_3.command", "1.3"),
        }
        and (
            payload.get("schema_id"),
            payload.get("schema_version"),
        )
        == (
            command.get("payload_schema_id"),
            command.get("payload_schema_version"),
        )
    )
    universal_status = (
        value.get("schema_id")
        == "kolibri.product.run.execution_status.v1_1"
        and value.get("schema_version") == "1.1"
    )
    if developer_command and not universal_status:
        _status_error("home_product_status_contract_invalid")
    if not (developer_command or standard_selection_command) and universal_status:
        _status_error("home_product_status_contract_invalid")
    profile_field = "runtime_profile" if universal_status else "profile"
    if frozenset(value) != frozenset(
        {
            "schema_id",
            "schema_version",
            "run_id",
            "status",
            profile_field,
            "execution_id",
            "verification_status",
            "result_text",
            "result_hash",
            "evidence",
            "error",
        }
    ):
        _status_error("home_product_status_contract_invalid")
    if universal_status:
        runtime_profile = _status_str(
            value.get(profile_field),
            code="home_product_status_contract_invalid",
            minimum=2,
            maximum=96,
            pattern=_RUNTIME_PROFILE_PATTERN,
        )
    else:
        if (
            value.get("schema_id")
            != "kolibri.product.run.execution_status"
            or value.get("schema_version") != "1.0"
            or value.get(profile_field) not in _PROFILES
        ):
            _status_error("home_product_status_contract_invalid")
        runtime_profile = str(value[profile_field])
    if (
        value.get("status") not in _RUN_STATES
        or value.get("verification_status") not in _VERIFICATION_STATES
    ):
        _status_error("home_product_status_contract_invalid")

    run_id = _status_str(
        value.get("run_id"),
        code="home_product_status_contract_invalid",
        maximum=160,
        pattern=_OPAQUE_ID_PATTERN,
    )
    execution_id = _status_str(
        value.get("execution_id"),
        code="home_product_status_contract_invalid",
        maximum=160,
        pattern=_OPAQUE_ID_PATTERN,
    )
    if run_id != payload.get("run_id"):
        _status_error("home_product_status_run_binding_invalid")
    requested_profile = (
        payload.get("runtime_profile")
        if developer_command
        else payload.get("preferred_agent_profile")
    )
    if (
        isinstance(requested_profile, str)
        and requested_profile != "auto"
        and runtime_profile != requested_profile
    ):
        _status_error("home_product_status_profile_binding_invalid")
    if (
        expected_profile is not None
        and runtime_profile != expected_profile
    ):
        _status_error("home_product_status_profile_changed")
    if (
        expected_execution_id is not None
        and execution_id != expected_execution_id
    ):
        _status_error("home_product_status_execution_changed")

    state = value["status"]
    verification = value["verification_status"]
    result_text = value["result_text"]
    result_hash = value["result_hash"]
    evidence = value["evidence"]
    error = value["error"]
    if state in {"accepted", "running"}:
        if verification != "not_applicable" or any(
            item is not None
            for item in (result_text, result_hash, evidence, error)
        ):
            _status_error("home_product_status_nonterminal_invalid")
    elif state == "succeeded":
        if (
            verification not in {"unverified", "verified"}
            or not isinstance(result_text, str)
            or not 1 <= len(result_text) <= 200_000
            or not result_text.strip()
            or not isinstance(result_hash, str)
            or not _SHA256_PATTERN.fullmatch(result_hash)
            or result_hash != _sha256_text(result_text)
            or error is not None
        ):
            _status_error("home_product_status_success_invalid")
        if verification == "unverified" and evidence is not None:
            _status_error("home_product_status_unverified_evidence_invalid")
        if verification == "verified" and evidence is None:
            _status_error("home_product_status_verified_evidence_missing")
        if evidence is not None:
            _validate_evidence(evidence, result_hash)
    else:
        if (
            verification != "not_applicable"
            or result_text is not None
            or result_hash is not None
            or evidence is not None
            or not isinstance(error, dict)
        ):
            _status_error("home_product_status_failure_invalid")
        _validate_error_envelope(error)
        if error.get("in_response_to") != execution_id:
            _status_error("home_product_status_error_binding_invalid")
    return dict(value)


def validate_product_goal_status(
    value: Mapping[str, Any],
    command: Mapping[str, Any],
    *,
    http_status: int | None = None,
) -> dict[str, Any]:
    """Validate a terminal Goal/ProjectCase initialization result."""

    if not isinstance(value, dict) or frozenset(value) != frozenset(
        {
            "schema_id",
            "schema_version",
            "run_id",
            "goal_id",
            "case_id",
            "status",
            "goal_version",
            "case_version",
            "error",
        }
    ):
        _status_error("home_product_goal_status_contract_invalid")
    if (
        value.get("schema_id")
        != "kolibri.product.goal.initialization_status"
        or value.get("schema_version") != "1.0"
        or value.get("status") not in {"initialized", "failed"}
    ):
        _status_error("home_product_goal_status_contract_invalid")
    run_id = _status_str(
        value.get("run_id"),
        code="home_product_goal_status_contract_invalid",
        maximum=160,
        pattern=_OPAQUE_ID_PATTERN,
    )
    goal_id = _status_str(
        value.get("goal_id"),
        code="home_product_goal_status_contract_invalid",
        maximum=160,
        pattern=_OPAQUE_ID_PATTERN,
    )
    case_id = _status_str(
        value.get("case_id"),
        code="home_product_goal_status_contract_invalid",
        maximum=160,
        pattern=_OPAQUE_ID_PATTERN,
    )
    payload = command.get("payload")
    if (
        not isinstance(payload, Mapping)
        or run_id != payload.get("run_id")
        or goal_id != payload.get("goal_id")
        or case_id != f"case_{goal_id}"
    ):
        _status_error("home_product_goal_status_binding_invalid")
    goal_version = value.get("goal_version")
    case_version = value.get("case_version")
    error = value.get("error")
    if value["status"] == "initialized":
        if (
            not _is_int(goal_version)
            or goal_version < 1
            or not _is_int(case_version)
            or case_version < 1
            or error is not None
            or (http_status is not None and http_status != 201)
        ):
            _status_error("home_product_goal_status_initialized_invalid")
    elif (
        goal_version is not None
        or case_version is not None
        or not isinstance(error, dict)
    ):
        _status_error("home_product_goal_status_failed_invalid")
    else:
        _validate_error_envelope(error)
        if error.get("in_response_to") != command.get("message_id"):
            _status_error("home_product_goal_status_error_binding_invalid")
        if (
            http_status is not None
            and error.get("http_status") != http_status
        ):
            _status_error("home_product_goal_status_http_binding_invalid")
    return dict(value)


def _validate_evidence(value: Any, result_hash: str) -> None:
    if not isinstance(value, dict) or frozenset(value) != frozenset(
        {"evidence_id", "evidence_version", "content_hash"}
    ):
        _status_error("home_product_status_evidence_invalid")
    _status_str(
        value.get("evidence_id"),
        code="home_product_status_evidence_invalid",
        maximum=160,
        pattern=_OPAQUE_ID_PATTERN,
    )
    if (
        not _is_int(value.get("evidence_version"))
        or value["evidence_version"] < 1
        or value.get("content_hash") != result_hash
    ):
        _status_error("home_product_status_evidence_invalid")


def _validate_error_envelope(value: dict[str, Any]) -> None:
    if frozenset(value) != frozenset(
        {
            "schema_id",
            "schema_version",
            "error_id",
            "in_response_to",
            "occurred_at",
            "http_status",
            "code",
            "category",
            "retryable",
            "retry_after_ms",
            "safe_message",
            "trace",
            "violations",
            "details",
        }
    ):
        _status_error("home_product_status_error_contract_invalid")
    if (
        value.get("schema_id") != "kolibri.error"
        or value.get("schema_version") != "1.0"
    ):
        _status_error("home_product_status_error_contract_invalid")
    _status_str(
        value.get("error_id"),
        code="home_product_status_error_contract_invalid",
        maximum=132,
        pattern=_ERROR_ID_PATTERN,
    )
    in_response_to = value.get("in_response_to")
    if in_response_to is not None and (
        not isinstance(in_response_to, str)
        or not 8 <= len(in_response_to) <= 160
    ):
        _status_error("home_product_status_error_contract_invalid")
    try:
        _require_datetime(
            value.get("occurred_at"),
            code="home_product_status_error_contract_invalid",
        )
    except HomeRuntimeCommandError:
        _status_error("home_product_status_error_contract_invalid")
    if (
        not _is_int(value.get("http_status"))
        or not 400 <= value["http_status"] <= 599
        or not isinstance(value.get("code"), str)
        or not _ERROR_CODE_PATTERN.fullmatch(value["code"])
        or value.get("category") not in _ERROR_CATEGORIES
        or not isinstance(value.get("retryable"), bool)
        or not isinstance(value.get("safe_message"), str)
        or not 1 <= len(value["safe_message"]) <= 500
        or not isinstance(value.get("details"), dict)
    ):
        _status_error("home_product_status_error_contract_invalid")
    retry_after = value.get("retry_after_ms")
    if retry_after is not None and (
        not _is_int(retry_after)
        or not 0 <= retry_after <= 86_400_000
        or value["retryable"] is not True
    ):
        _status_error("home_product_status_error_contract_invalid")
    if value["retryable"] is False and retry_after is not None:
        _status_error("home_product_status_error_contract_invalid")
    _validate_status_trace(value.get("trace"))
    violations = value.get("violations")
    if not isinstance(violations, list) or len(violations) > 100:
        _status_error("home_product_status_error_contract_invalid")
    for violation in violations:
        if not isinstance(violation, dict) or frozenset(violation) != frozenset(
            {"path", "code", "message"}
        ):
            _status_error("home_product_status_error_contract_invalid")
        if (
            not isinstance(violation.get("path"), str)
            or len(violation["path"]) > 240
            or not isinstance(violation.get("code"), str)
            or not _ERROR_CODE_PATTERN.fullmatch(violation["code"])
            or not isinstance(violation.get("message"), str)
            or len(violation["message"]) > 300
        ):
            _status_error("home_product_status_error_contract_invalid")


def _validate_status_trace(value: Any) -> None:
    if not isinstance(value, dict) or frozenset(value) != frozenset(
        {
            "trace_id",
            "span_id",
            "parent_span_id",
            "correlation_id",
            "causation_id",
        }
    ):
        _status_error("home_product_status_error_contract_invalid")
    parent = value.get("parent_span_id")
    causation = value.get("causation_id")
    if (
        not isinstance(value.get("trace_id"), str)
        or not _TRACE_ID_PATTERN.fullmatch(value["trace_id"])
        or not isinstance(value.get("span_id"), str)
        or not _SPAN_ID_PATTERN.fullmatch(value["span_id"])
        or (
            parent is not None
            and (
                not isinstance(parent, str)
                or not _SPAN_ID_PATTERN.fullmatch(parent)
            )
        )
        or not isinstance(value.get("correlation_id"), str)
        or not 8 <= len(value["correlation_id"]) <= 160
        or (
            causation is not None
            and (
                not isinstance(causation, str)
                or not 8 <= len(causation) <= 160
            )
        )
    ):
        _status_error("home_product_status_error_contract_invalid")


def _post_home_command(
    *,
    settings: HomeRuntimeSettings,
    command_url: str,
    transport: httpx.BaseTransport | None,
    command_bytes: bytes,
    command: Mapping[str, Any],
    accept_failed_status_body: bool = False,
) -> HomeRuntimeResponse:
    logical_path = urlsplit(command_url).path
    identity_headers = product_identity_headers(
        settings.identity_hmac_key,
        settings.identity_hmac_key_id,
        command,
        command_bytes,
        method="POST",
        logical_path=logical_path,
    )
    idempotency = command.get("idempotency")
    if not isinstance(idempotency, Mapping) or not isinstance(
        idempotency.get("key"),
        str,
    ):
        raise HomeRuntimeCommandError(
            "home_product_command_idempotency_invalid"
        )
    service_scope = {
        "product.run.execute": "product-runs:execute",
        "product.goal.initialize": "product-goals:initialize",
        "product.provider.enrollment.request": (
            "provider-connections:enroll"
        ),
    }.get(str(command.get("command_name")))
    if service_scope is None:
        raise HomeRuntimeCommandError(
            "home_product_command_contract_invalid"
        )
    headers = {
        "Authorization": f"Bearer {settings.bearer_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Idempotency-Key": str(idempotency["key"]),
        "X-Kolibri-Service-Scope": service_scope,
        **identity_headers,
    }
    try:
        with httpx.Client(
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            with client.stream(
                "POST",
                command_url,
                headers=headers,
                content=command_bytes,
            ) as response:
                success_status = 200 <= response.status_code < 300
                accepted_failure_status = (
                    accept_failed_status_body
                    and 400 <= response.status_code < 600
                )
                if not success_status and not accepted_failure_status:
                    raise HomeRuntimeTransportError(
                        f"home_product_http_{response.status_code}",
                        retryable=(
                            response.status_code in _RETRYABLE_HTTP_STATUSES
                        ),
                        infrastructure_outage=(
                            response.status_code in {502, 503, 504}
                        ),
                    )
                media_type = response.headers.get(
                    "content-type", ""
                ).split(";", 1)[0].strip().lower()
                if media_type != "application/json":
                    _raise_response_shape_error(
                        response.status_code,
                        accept_failed_status_body=accept_failed_status_body,
                        code="home_product_status_content_type_invalid",
                    )
                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        declared_size = int(content_length)
                    except ValueError:
                        _raise_response_shape_error(
                            response.status_code,
                            accept_failed_status_body=(
                                accept_failed_status_body
                            ),
                            code="home_product_status_length_invalid",
                        )
                    if (
                        declared_size < 0
                        or declared_size > settings.max_response_bytes
                    ):
                        _raise_response_shape_error(
                            response.status_code,
                            accept_failed_status_body=(
                                accept_failed_status_body
                            ),
                            code="home_product_status_too_large",
                        )
                response_bytes = bytearray()
                for chunk in response.iter_bytes():
                    if (
                        len(response_bytes) + len(chunk)
                        > settings.max_response_bytes
                    ):
                        _raise_response_shape_error(
                            response.status_code,
                            accept_failed_status_body=(
                                accept_failed_status_body
                            ),
                            code="home_product_status_too_large",
                        )
                    response_bytes.extend(chunk)
                http_status = response.status_code
    except HomeRuntimeError:
        raise
    except (httpx.TimeoutException, httpx.RequestError):
        raise HomeRuntimeTransportError(
            "home_product_unreachable",
            retryable=True,
            infrastructure_outage=True,
        ) from None

    exact_bytes = bytes(response_bytes)
    try:
        body_text = exact_bytes.decode("utf-8", "strict")
    except UnicodeDecodeError:
        if (
            accept_failed_status_body
            and http_status in _RETRYABLE_HTTP_STATUSES
        ):
            raise HomeRuntimeTransportError(
                f"home_product_http_{http_status}",
                retryable=True,
                infrastructure_outage=http_status in {502, 503, 504},
            ) from None
        raise HomeRuntimeStatusError(
            "home_product_status_json_invalid"
        ) from None
    try:
        value = _decode_json_object(
            exact_bytes,
            invalid_code="home_product_status_json_invalid",
        )
    except HomeRuntimeCommandError:
        if (
            accept_failed_status_body
            and http_status in _RETRYABLE_HTTP_STATUSES
        ):
            raise HomeRuntimeTransportError(
                f"home_product_http_{http_status}",
                retryable=True,
                infrastructure_outage=http_status in {502, 503, 504},
            ) from None
        raise HomeRuntimeStatusError(
            "home_product_status_json_invalid"
        ) from None
    return HomeRuntimeResponse(
        http_status=http_status,
        body_text=body_text,
        value=value,
    )


def _raise_response_shape_error(
    http_status: int,
    *,
    accept_failed_status_body: bool,
    code: str,
) -> None:
    if (
        accept_failed_status_body
        and http_status in _RETRYABLE_HTTP_STATUSES
    ):
        raise HomeRuntimeTransportError(
            f"home_product_http_{http_status}",
            retryable=True,
            infrastructure_outage=http_status in {502, 503, 504},
        )
    raise HomeRuntimeStatusError(code)


class HomeProductRunClient:
    """Authenticated, byte-stable run command delivery to Logical Home."""

    def __init__(
        self,
        settings: HomeRuntimeSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    def execute_with_metadata(
        self,
        stored_command: str | bytes,
        *,
        expected_execution_id: str | None = None,
        expected_profile: str | None = None,
    ) -> HomeRuntimeResponse:
        """Return validated status with exact response bytes preserved as text."""

        command_bytes, command = parse_stored_product_command(stored_command)
        response = _post_home_command(
            settings=self.settings,
            command_url=self.settings.command_url,
            transport=self.transport,
            command_bytes=command_bytes,
            command=command,
        )
        value = validate_product_execution_status(
            response.value,
            command,
            expected_execution_id=expected_execution_id,
            expected_profile=expected_profile,
        )
        return HomeRuntimeResponse(
            http_status=response.http_status,
            body_text=response.body_text,
            value=value,
        )

    def execute_stored_command(
        self,
        stored_command: str | bytes,
        *,
        expected_execution_id: str | None = None,
        expected_profile: str | None = None,
    ) -> dict[str, Any]:
        """POST exact outbox bytes and return a fully validated run status."""

        return self.execute_with_metadata(
            stored_command,
            expected_execution_id=expected_execution_id,
            expected_profile=expected_profile,
        ).value

    def execute(
        self,
        stored_command: str | bytes,
        expected_execution_id: str | None = None,
        expected_profile: str | None = None,
    ) -> dict[str, Any]:
        """Compatibility alias for worker call sites."""

        return self.execute_stored_command(
            stored_command,
            expected_execution_id=expected_execution_id,
            expected_profile=expected_profile,
        )


class HomeProductGoalClient:
    """Authenticated, byte-stable Goal initialization delivery."""

    def __init__(
        self,
        settings: HomeRuntimeSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    def execute_with_metadata(
        self,
        stored_command: str | bytes,
    ) -> HomeRuntimeResponse:
        command_bytes, command = parse_stored_goal_command(stored_command)
        goal_url = self.settings.goal_command_url
        if goal_url is None:
            raise HomeRuntimeConfigurationError(
                "home_product_goal_command_url_missing"
            )
        response = _post_home_command(
            settings=self.settings,
            command_url=goal_url,
            transport=self.transport,
            command_bytes=command_bytes,
            command=command,
            accept_failed_status_body=True,
        )
        try:
            value = validate_product_goal_status(
                response.value,
                command,
                http_status=response.http_status,
            )
        except HomeRuntimeStatusError:
            if response.http_status in _RETRYABLE_HTTP_STATUSES:
                raise HomeRuntimeTransportError(
                    f"home_product_http_{response.http_status}",
                    retryable=True,
                    infrastructure_outage=(
                        response.http_status in {502, 503, 504}
                    ),
                ) from None
            raise
        return HomeRuntimeResponse(
            http_status=response.http_status,
            body_text=response.body_text,
            value=value,
        )

    def execute_stored_command(
        self,
        stored_command: str | bytes,
    ) -> dict[str, Any]:
        return self.execute_with_metadata(stored_command).value

    def execute(
        self,
        stored_command: str | bytes,
    ) -> dict[str, Any]:
        return self.execute_stored_command(stored_command)
