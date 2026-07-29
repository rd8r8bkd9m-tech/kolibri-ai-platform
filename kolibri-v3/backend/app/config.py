from __future__ import annotations

import os
import re
import secrets
import stat
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


_OPAQUE_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]{1,31}_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$"
)
_CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
_CONTROL_IDENTITY_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$"
)
_PRODUCT_GOAL_INITIALIZE_CAPABILITY = "product.goal.initialize.request"
_PRODUCT_RUN_EXECUTE_CAPABILITY = "product.run.execute.request"
_PRODUCT_DEVELOPER_RUN_EXECUTE_CAPABILITY = (
    "product.developer.run.execute.request"
)
_PRODUCT_PROVIDER_ENROLLMENT_CAPABILITY = (
    "product.provider.enrollment.request"
)
_REQUIRED_PRODUCT_AUTHORITY_CAPABILITIES = frozenset(
    {
        _PRODUCT_GOAL_INITIALIZE_CAPABILITY,
        _PRODUCT_RUN_EXECUTE_CAPABILITY,
        _PRODUCT_PROVIDER_ENROLLMENT_CAPABILITY,
    }
)


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("boolean configuration value is invalid")


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _optional_int(value: str | None, *, name: str) -> int | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    try:
        return int(normalized)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _parse_float(value: str | None, *, default: float, name: str) -> float:
    normalized = _optional_text(value)
    if normalized is None:
        return default
    try:
        return float(normalized)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _parse_int(value: str | None, *, default: int, name: str) -> int:
    normalized = _optional_text(value)
    if normalized is None:
        return default
    try:
        return int(normalized)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _parse_capabilities(
    value: str | None,
    *,
    include_developer_default: bool = False,
) -> tuple[str, ...]:
    if value is None:
        capabilities = [
            _PRODUCT_GOAL_INITIALIZE_CAPABILITY,
            _PRODUCT_RUN_EXECUTE_CAPABILITY,
            _PRODUCT_PROVIDER_ENROLLMENT_CAPABILITY,
        ]
        if include_developer_default:
            capabilities.append(_PRODUCT_DEVELOPER_RUN_EXECUTE_CAPABILITY)
        return tuple(capabilities)
    return tuple(
        dict.fromkeys(
            capability.strip()
            for capability in value.split(",")
            if capability.strip()
        )
    )


def _development_csrf_secret(database_url: str) -> bytes:
    configured = os.getenv("KOLIBRI_V3_CSRF_SECRET_FILE", "").strip()
    if configured:
        secret_path = Path(configured)
    else:
        database_path = Path(database_url.removeprefix("sqlite:///"))
        secret_path = database_path.parent / ".kolibri-v3-csrf-secret"
    if not secret_path.is_absolute():
        secret_path = (Path.cwd() / secret_path).resolve()
    secret_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(secret_path, flags)
    except FileNotFoundError:
        candidate = secrets.token_bytes(32)
        create_flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(secret_path, create_flags, 0o600)
        except FileExistsError:
            descriptor = os.open(secret_path, flags)
        else:
            try:
                os.write(descriptor, candidate)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            descriptor = os.open(secret_path, flags)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_mode & 0o077
            or metadata.st_size != 32
        ):
            raise ValueError("development CSRF secret file is unsafe")
        value = os.read(descriptor, 33)
    finally:
        os.close(descriptor)
    if len(value) != 32:
        raise ValueError("development CSRF secret file is invalid")
    return value


def normalize_origin(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("allowed origins must be exact HTTP(S) origins")

    hostname = parsed.hostname.lower().rstrip(".")
    host = f"[{hostname}]" if ":" in hostname else hostname
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return f"{parsed.scheme.lower()}://{host}"


def _normalize_bootstrap_email(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    if not normalized:
        return None
    if len(normalized) > 320 or "@" not in normalized:
        raise ValueError("bootstrap owner email is invalid")
    return normalized


@dataclass(frozen=True, slots=True)
class ProductAuthorityGrant:
    """Non-secret Product/Data Authority claim verified by Logical Home.

    The grant is server-owned metadata, not proof of authority. The bearer and
    identity-HMAC secrets intentionally live only in the standalone transport
    worker and are never part of application settings or persisted records.
    """

    authority_id: str
    authority_epoch: int
    authority_placement_id: str
    authorization_decision_id: str
    capabilities: tuple[str, ...]

    def as_identity_authority(self) -> dict[str, Any]:
        return {
            "authority_id": self.authority_id,
            "authority_role": "product_data_authority",
            "authority_epoch": self.authority_epoch,
            "authority_placement_id": self.authority_placement_id,
            "authorization_decision_id": self.authorization_decision_id,
            "capabilities": list(self.capabilities),
        }


@dataclass(frozen=True, slots=True)
class Settings:
    """Server-owned configuration for the isolated Kolibri V3 backend.

    Public registration always creates an isolated tenant and an unprivileged
    user. Platform-owner elevation is an explicit out-of-band server operation;
    requests can never supply or infer a role or tenant id.
    """

    database_url: str = "sqlite:///./var/kolibri-v3.db"
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:3103",
        "http://localhost:3103",
    )
    bootstrap_owner_email: str | None = None
    environment: str = "development"
    cookie_secure: bool = False
    session_cookie_name: str = "kolibri_v3_session"
    csrf_cookie_name: str = "kolibri_v3_csrf"
    session_ttl_seconds: int = 7 * 24 * 60 * 60
    csrf_secret: bytes = field(default_factory=lambda: secrets.token_bytes(32))
    product_authority_id: str | None = None
    product_authority_epoch: int | None = None
    product_authority_placement_id: str | None = None
    product_authorization_decision_id: str | None = None
    product_authority_capabilities: tuple[str, ...] = (
        _PRODUCT_GOAL_INITIALIZE_CAPABILITY,
        _PRODUCT_RUN_EXECUTE_CAPABILITY,
        _PRODUCT_PROVIDER_ENROLLMENT_CAPABILITY,
    )
    product_run_request_timeout_seconds: float = 10.0
    product_run_lease_seconds: float = 30.0
    product_run_poll_seconds: float = 0.1
    product_run_retry_base_seconds: float = 1.0
    product_run_retry_max_seconds: float = 60.0
    product_run_idle_seconds: float = 0.25
    product_run_max_attempts: int = 8
    product_run_command_deadline_seconds: int = 15 * 60
    provider_enrollment_max_attempts: int = 8
    provider_enrollment_command_deadline_seconds: int = 15 * 60
    provider_enrollment_lease_seconds: float = 30.0
    provider_enrollment_retry_base_seconds: float = 2.0
    provider_enrollment_retry_max_seconds: float = 300.0
    provider_enrollment_idle_seconds: float = 0.5
    provider_authority_dispatch_configured: bool = False
    provider_enrollment_reauth_seconds: int = 15 * 60
    direct_model_runtime_enabled: bool = False
    direct_model_timeout_seconds: float = 180.0
    developer_agent_enabled: bool = False
    developer_workspace_root: Path | None = None
    developer_agent_timeout_seconds: float = 30 * 60
    provider_execution_enabled: bool = False
    provider_execution_workspace_root: Path | None = None
    provider_execution_workspace_ref: str = "repository"
    provider_execution_allowed_node_id: str | None = None
    provider_execution_allowed_agent_id: str | None = None
    provider_execution_allowed_slot_id: str | None = None
    provider_execution_timeout_seconds: float = 30 * 60
    provider_execution_allowed_tool_ids: tuple[str, ...] = (
        "tool.filesystem.full",
        "tool.network.full",
        "tool.repository.read",
        "tool.repository.write",
        "tool.shell.full",
        "tool.shell.workspace",
    )
    provider_execution_card_version: int = 1
    provider_execution_card_updated_at: str = (
        "2026-07-29T00:00:00+00:00"
    )
    fgis_pricing_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("Kolibri V3 currently accepts only sqlite:/// URLs")

        normalized_origins = tuple(
            dict.fromkeys(normalize_origin(origin) for origin in self.allowed_origins)
        )
        if not normalized_origins or any(origin == "*" for origin in normalized_origins):
            raise ValueError("CORS origins must be an explicit non-wildcard allowlist")
        object.__setattr__(self, "allowed_origins", normalized_origins)

        environment = self.environment.strip().lower()
        if environment not in {"development", "test", "production"}:
            raise ValueError("environment must be development, test, or production")
        object.__setattr__(self, "environment", environment)
        object.__setattr__(
            self,
            "bootstrap_owner_email",
            _normalize_bootstrap_email(self.bootstrap_owner_email),
        )

        if not (300 <= self.session_ttl_seconds <= 30 * 24 * 60 * 60):
            raise ValueError("session TTL must be between 5 minutes and 30 days")
        if len(self.csrf_secret) < 32:
            raise ValueError("CSRF secret must contain at least 32 bytes")
        if not self.session_cookie_name or not self.csrf_cookie_name:
            raise ValueError("cookie names cannot be empty")
        if self.session_cookie_name == self.csrf_cookie_name:
            raise ValueError("session and CSRF cookies must use different names")
        if self.environment == "production" and not self.cookie_secure:
            raise ValueError("production session cookies must be Secure")
        if self.environment == "production" and any(
            not origin.startswith("https://") for origin in normalized_origins
        ):
            raise ValueError("production CORS origins must use HTTPS")

        capabilities = tuple(
            dict.fromkeys(
                capability.strip()
                for capability in self.product_authority_capabilities
                if capability.strip()
            )
        )
        if (
            not capabilities
            or not _REQUIRED_PRODUCT_AUTHORITY_CAPABILITIES.issubset(capabilities)
            or any(
                _CAPABILITY_PATTERN.fullmatch(capability) is None
                for capability in capabilities
            )
        ):
            raise ValueError(
                "Product authority capabilities must include the goal initialization "
                "run execution and provider enrollment capabilities and contain "
                "only valid names"
            )
        object.__setattr__(self, "product_authority_capabilities", capabilities)

        authority_fields = (
            self.product_authority_id,
            self.product_authority_epoch,
            self.product_authority_placement_id,
            self.product_authorization_decision_id,
        )
        has_authority = all(value is not None for value in authority_fields)
        if any(value is not None for value in authority_fields) and not has_authority:
            raise ValueError("Product authority grant metadata must be configured together")
        if self.environment == "production" and not has_authority:
            raise ValueError(
                "Product authority grant metadata is required in production"
            )
        if has_authority:
            opaque_values = (
                self.product_authority_id,
                self.product_authority_placement_id,
                self.product_authorization_decision_id,
            )
            if any(
                not isinstance(value, str)
                or _OPAQUE_ID_PATTERN.fullmatch(value) is None
                for value in opaque_values
            ):
                raise ValueError("Product authority grant contains an invalid opaque id")
            if (
                not isinstance(self.product_authority_epoch, int)
                or isinstance(self.product_authority_epoch, bool)
                or self.product_authority_epoch < 1
            ):
                raise ValueError("Product authority epoch must be a positive integer")

        if not (
            0.25 <= self.product_run_request_timeout_seconds <= 60
            and 5 <= self.product_run_lease_seconds <= 300
            and self.product_run_lease_seconds
            >= self.product_run_request_timeout_seconds + 1
            and 0.05 <= self.product_run_poll_seconds <= 30
            and 0.1 <= self.product_run_retry_base_seconds <= 60
            and self.product_run_retry_base_seconds
            <= self.product_run_retry_max_seconds
            <= 3600
            and 0.05 <= self.product_run_idle_seconds <= 30
            and 1 <= self.product_run_max_attempts <= 100
            and 60 <= self.product_run_command_deadline_seconds <= 3600
        ):
            raise ValueError("Product run worker timing configuration is invalid")
        if not (
            1 <= self.provider_enrollment_max_attempts <= 100
            and 60
            <= self.provider_enrollment_command_deadline_seconds
            <= 3600
            and 5 <= self.provider_enrollment_lease_seconds <= 300
            and 0.1 <= self.provider_enrollment_retry_base_seconds <= 60
            and self.provider_enrollment_retry_base_seconds
            <= self.provider_enrollment_retry_max_seconds
            <= 3600
            and 0.05 <= self.provider_enrollment_idle_seconds <= 30
            and 60 <= self.provider_enrollment_reauth_seconds <= 3600
        ):
            raise ValueError(
                "Provider enrollment worker timing configuration is invalid"
            )
        if not 10 <= self.direct_model_timeout_seconds <= 600:
            raise ValueError("Direct model timeout must be between 10 and 600 seconds")
        if not 60 <= self.developer_agent_timeout_seconds <= 3600:
            raise ValueError(
                "Developer agent timeout must be between 60 and 3600 seconds"
            )
        if self.developer_agent_enabled:
            if self.environment == "production":
                raise ValueError(
                    "Local developer agent cannot run in production; use "
                    "Provider Execution Authority"
                )
            if not self.direct_model_runtime_enabled:
                raise ValueError(
                    "Developer agent requires the direct model runtime"
                )
            if self.developer_workspace_root is None:
                raise ValueError(
                    "Developer agent workspace root is required"
                )
            workspace_root = self.developer_workspace_root.expanduser().resolve()
            if not workspace_root.is_dir():
                raise ValueError(
                    "Developer agent workspace root must be an existing directory"
                )
            object.__setattr__(
                self,
                "developer_workspace_root",
                workspace_root,
            )
        if not 60 <= self.provider_execution_timeout_seconds <= 3600:
            raise ValueError(
                "Provider execution timeout must be between 60 and 3600 seconds"
            )
        provider_tool_ids = tuple(
            dict.fromkeys(
                tool_id.strip()
                for tool_id in self.provider_execution_allowed_tool_ids
                if tool_id.strip()
            )
        )
        if (
            not provider_tool_ids
            or len(provider_tool_ids) > 64
            or any(
                _CAPABILITY_PATTERN.fullmatch(tool_id) is None
                for tool_id in provider_tool_ids
            )
        ):
            raise ValueError("Provider execution tool allowlist is invalid")
        object.__setattr__(
            self,
            "provider_execution_allowed_tool_ids",
            provider_tool_ids,
        )
        if not 1 <= self.provider_execution_card_version <= 1_000_000:
            raise ValueError("Provider execution card version is invalid")
        try:
            card_updated_at = datetime.fromisoformat(
                self.provider_execution_card_updated_at.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError(
                "Provider execution card timestamp is invalid"
            ) from exc
        if card_updated_at.tzinfo is None:
            raise ValueError("Provider execution card timestamp requires timezone")
        if self.provider_execution_enabled:
            if (
                self.provider_execution_allowed_node_id is None
                or _CONTROL_IDENTITY_PATTERN.fullmatch(
                    self.provider_execution_allowed_node_id
                )
                is None
                or self.provider_execution_allowed_agent_id is None
                or _CONTROL_IDENTITY_PATTERN.fullmatch(
                    self.provider_execution_allowed_agent_id
                )
                is None
                or self.provider_execution_allowed_slot_id is None
                or _CONTROL_IDENTITY_PATTERN.fullmatch(
                    self.provider_execution_allowed_slot_id
                )
                is None
            ):
                raise ValueError(
                    "Provider execution caller identity is required"
                )
            if self.provider_execution_workspace_ref != "repository":
                raise ValueError(
                    "Provider execution workspace reference must be repository"
                )
            if self.provider_execution_workspace_root is None:
                raise ValueError(
                    "Provider execution workspace root is required"
                )
            provider_workspace_root = (
                self.provider_execution_workspace_root.expanduser().resolve()
            )
            if not provider_workspace_root.is_dir():
                raise ValueError(
                    "Provider execution workspace root must be an existing directory"
                )
            object.__setattr__(
                self,
                "provider_execution_workspace_root",
                provider_workspace_root,
            )

    def require_product_authority_grant(self) -> ProductAuthorityGrant:
        """Return a complete server-owned grant or fail before accepting a run."""

        if (
            self.product_authority_id is None
            or self.product_authority_epoch is None
            or self.product_authority_placement_id is None
            or self.product_authorization_decision_id is None
        ):
            raise RuntimeError("Product authority grant is not configured")
        return ProductAuthorityGrant(
            authority_id=self.product_authority_id,
            authority_epoch=self.product_authority_epoch,
            authority_placement_id=self.product_authority_placement_id,
            authorization_decision_id=self.product_authorization_decision_id,
            capabilities=self.product_authority_capabilities,
        )

    @classmethod
    def from_env(cls) -> "Settings":
        environment = os.getenv("KOLIBRI_V3_ENV", "development").strip().lower()
        database_url = os.getenv(
            "KOLIBRI_V3_DATABASE_URL", "sqlite:///./var/kolibri-v3.db"
        ).strip()
        raw_origins = os.getenv(
            "KOLIBRI_V3_ALLOWED_ORIGINS",
            "http://127.0.0.1:3103,http://localhost:3103",
        )
        origins = tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip())

        raw_secret = os.getenv("KOLIBRI_V3_CSRF_SECRET")
        if environment == "production" and not raw_secret:
            raise ValueError("KOLIBRI_V3_CSRF_SECRET is required in production")
        csrf_secret = (
            raw_secret.encode("utf-8")
            if raw_secret is not None
            else _development_csrf_secret(database_url)
        )

        default_workspace_root = Path(__file__).resolve().parents[3]
        configured_workspace_root = _optional_text(
            os.getenv("KOLIBRI_V3_DEVELOPER_WORKSPACE_ROOT")
        )
        provider_execution_enabled = _parse_bool(
            os.getenv("KOLIBRI_V3_PROVIDER_EXECUTION_ENABLED"),
            default=False,
        )
        configured_provider_workspace_root = _optional_text(
            os.getenv("KOLIBRI_V3_PROVIDER_EXECUTION_WORKSPACE_ROOT")
        )
        developer_agent_enabled = _parse_bool(
            os.getenv("KOLIBRI_V3_DEVELOPER_AGENT_ENABLED"),
            default=environment == "development",
        )
        return cls(
            database_url=database_url,
            allowed_origins=origins,
            bootstrap_owner_email=os.getenv("KOLIBRI_V3_BOOTSTRAP_OWNER_EMAIL"),
            environment=environment,
            cookie_secure=_parse_bool(
                os.getenv("KOLIBRI_V3_COOKIE_SECURE"),
                default=environment == "production",
            ),
            direct_model_runtime_enabled=_parse_bool(
                os.getenv("KOLIBRI_V3_DIRECT_MODEL_RUNTIME"),
                default=environment == "development",
            ),
            direct_model_timeout_seconds=_parse_float(
                os.getenv("KOLIBRI_V3_DIRECT_MODEL_TIMEOUT_SECONDS"),
                default=180.0,
                name="KOLIBRI_V3_DIRECT_MODEL_TIMEOUT_SECONDS",
            ),
            developer_agent_enabled=developer_agent_enabled,
            developer_workspace_root=(
                Path(configured_workspace_root)
                if configured_workspace_root is not None
                else default_workspace_root
            ),
            developer_agent_timeout_seconds=_parse_float(
                os.getenv("KOLIBRI_V3_DEVELOPER_AGENT_TIMEOUT_SECONDS"),
                default=30 * 60,
                name="KOLIBRI_V3_DEVELOPER_AGENT_TIMEOUT_SECONDS",
            ),
            provider_execution_enabled=provider_execution_enabled,
            provider_execution_workspace_root=(
                Path(configured_provider_workspace_root)
                if configured_provider_workspace_root is not None
                else default_workspace_root
            ),
            provider_execution_workspace_ref=os.getenv(
                "KOLIBRI_V3_PROVIDER_EXECUTION_WORKSPACE_REF",
                "repository",
            ).strip(),
            provider_execution_allowed_node_id=_optional_text(
                os.getenv("KOLIBRI_V3_PROVIDER_EXECUTION_ALLOWED_NODE_ID")
            ),
            provider_execution_allowed_agent_id=_optional_text(
                os.getenv("KOLIBRI_V3_PROVIDER_EXECUTION_ALLOWED_AGENT_ID")
            ),
            provider_execution_allowed_slot_id=_optional_text(
                os.getenv(
                    "KOLIBRI_V3_PROVIDER_EXECUTION_ALLOWED_SLOT_ID"
                )
            ),
            provider_execution_timeout_seconds=_parse_float(
                os.getenv("KOLIBRI_V3_PROVIDER_EXECUTION_TIMEOUT_SECONDS"),
                default=30 * 60,
                name="KOLIBRI_V3_PROVIDER_EXECUTION_TIMEOUT_SECONDS",
            ),
            provider_execution_allowed_tool_ids=tuple(
                item.strip()
                for item in os.getenv(
                    "KOLIBRI_V3_PROVIDER_EXECUTION_ALLOWED_TOOL_IDS",
                    (
                        "tool.filesystem.full,tool.network.full,"
                        "tool.repository.read,tool.repository.write,"
                        "tool.shell.full,tool.shell.workspace"
                    ),
                ).split(",")
                if item.strip()
            ),
            provider_execution_card_version=_parse_int(
                os.getenv("KOLIBRI_V3_PROVIDER_EXECUTION_CARD_VERSION"),
                default=1,
                name="KOLIBRI_V3_PROVIDER_EXECUTION_CARD_VERSION",
            ),
            provider_execution_card_updated_at=os.getenv(
                "KOLIBRI_V3_PROVIDER_EXECUTION_CARD_UPDATED_AT",
                "2026-07-29T00:00:00+00:00",
            ).strip(),
            fgis_pricing_enabled=_parse_bool(
                os.getenv("KOLIBRI_V3_FGIS_PRICING_ENABLED"),
                default=environment != "production",
            ),
            session_cookie_name=os.getenv(
                "KOLIBRI_V3_SESSION_COOKIE_NAME", "kolibri_v3_session"
            ).strip(),
            csrf_cookie_name=os.getenv(
                "KOLIBRI_V3_CSRF_COOKIE_NAME", "kolibri_v3_csrf"
            ).strip(),
            session_ttl_seconds=int(
                os.getenv("KOLIBRI_V3_SESSION_TTL_SECONDS", str(7 * 24 * 60 * 60))
            ),
            csrf_secret=csrf_secret,
            product_authority_id=_optional_text(
                os.getenv("KOLIBRI_V3_PRODUCT_AUTHORITY_ID")
            ),
            product_authority_epoch=_optional_int(
                os.getenv("KOLIBRI_V3_PRODUCT_AUTHORITY_EPOCH"),
                name="KOLIBRI_V3_PRODUCT_AUTHORITY_EPOCH",
            ),
            product_authority_placement_id=_optional_text(
                os.getenv("KOLIBRI_V3_PRODUCT_AUTHORITY_PLACEMENT_ID")
            ),
            product_authorization_decision_id=_optional_text(
                os.getenv("KOLIBRI_V3_PRODUCT_AUTHORIZATION_DECISION_ID")
            ),
            product_authority_capabilities=_parse_capabilities(
                os.getenv("KOLIBRI_V3_PRODUCT_AUTHORITY_CAPABILITIES"),
                include_developer_default=environment != "production",
            ),
            product_run_request_timeout_seconds=_parse_float(
                os.getenv("KOLIBRI_V3_PRODUCT_RUN_REQUEST_TIMEOUT_SECONDS"),
                default=10.0,
                name="KOLIBRI_V3_PRODUCT_RUN_REQUEST_TIMEOUT_SECONDS",
            ),
            product_run_lease_seconds=_parse_float(
                os.getenv("KOLIBRI_V3_PRODUCT_RUN_LEASE_SECONDS"),
                default=30.0,
                name="KOLIBRI_V3_PRODUCT_RUN_LEASE_SECONDS",
            ),
            product_run_poll_seconds=_parse_float(
                os.getenv("KOLIBRI_V3_PRODUCT_RUN_POLL_SECONDS"),
                default=0.1,
                name="KOLIBRI_V3_PRODUCT_RUN_POLL_SECONDS",
            ),
            product_run_retry_base_seconds=_parse_float(
                os.getenv("KOLIBRI_V3_PRODUCT_RUN_RETRY_BASE_SECONDS"),
                default=1.0,
                name="KOLIBRI_V3_PRODUCT_RUN_RETRY_BASE_SECONDS",
            ),
            product_run_retry_max_seconds=_parse_float(
                os.getenv("KOLIBRI_V3_PRODUCT_RUN_RETRY_MAX_SECONDS"),
                default=60.0,
                name="KOLIBRI_V3_PRODUCT_RUN_RETRY_MAX_SECONDS",
            ),
            product_run_idle_seconds=_parse_float(
                os.getenv("KOLIBRI_V3_PRODUCT_RUN_IDLE_SECONDS"),
                default=0.25,
                name="KOLIBRI_V3_PRODUCT_RUN_IDLE_SECONDS",
            ),
            product_run_max_attempts=_parse_int(
                os.getenv("KOLIBRI_V3_PRODUCT_RUN_MAX_ATTEMPTS"),
                default=8,
                name="KOLIBRI_V3_PRODUCT_RUN_MAX_ATTEMPTS",
            ),
            product_run_command_deadline_seconds=_parse_int(
                os.getenv("KOLIBRI_V3_PRODUCT_RUN_COMMAND_DEADLINE_SECONDS"),
                default=15 * 60,
                name="KOLIBRI_V3_PRODUCT_RUN_COMMAND_DEADLINE_SECONDS",
            ),
            provider_enrollment_max_attempts=_parse_int(
                os.getenv("KOLIBRI_V3_PROVIDER_ENROLLMENT_MAX_ATTEMPTS"),
                default=8,
                name="KOLIBRI_V3_PROVIDER_ENROLLMENT_MAX_ATTEMPTS",
            ),
            provider_enrollment_command_deadline_seconds=_parse_int(
                os.getenv(
                    "KOLIBRI_V3_PROVIDER_ENROLLMENT_COMMAND_DEADLINE_SECONDS"
                ),
                default=15 * 60,
                name=(
                    "KOLIBRI_V3_PROVIDER_ENROLLMENT_COMMAND_DEADLINE_SECONDS"
                ),
            ),
            provider_enrollment_lease_seconds=_parse_float(
                os.getenv("KOLIBRI_V3_PROVIDER_ENROLLMENT_LEASE_SECONDS"),
                default=30.0,
                name="KOLIBRI_V3_PROVIDER_ENROLLMENT_LEASE_SECONDS",
            ),
            provider_enrollment_retry_base_seconds=_parse_float(
                os.getenv(
                    "KOLIBRI_V3_PROVIDER_ENROLLMENT_RETRY_BASE_SECONDS"
                ),
                default=2.0,
                name="KOLIBRI_V3_PROVIDER_ENROLLMENT_RETRY_BASE_SECONDS",
            ),
            provider_enrollment_retry_max_seconds=_parse_float(
                os.getenv(
                    "KOLIBRI_V3_PROVIDER_ENROLLMENT_RETRY_MAX_SECONDS"
                ),
                default=300.0,
                name="KOLIBRI_V3_PROVIDER_ENROLLMENT_RETRY_MAX_SECONDS",
            ),
            provider_enrollment_idle_seconds=_parse_float(
                os.getenv("KOLIBRI_V3_PROVIDER_ENROLLMENT_IDLE_SECONDS"),
                default=0.5,
                name="KOLIBRI_V3_PROVIDER_ENROLLMENT_IDLE_SECONDS",
            ),
            provider_authority_dispatch_configured=_parse_bool(
                os.getenv(
                    "KOLIBRI_V3_PROVIDER_AUTHORITY_DISPATCH_CONFIGURED"
                ),
                default=False,
            ),
            provider_enrollment_reauth_seconds=_parse_int(
                os.getenv("KOLIBRI_V3_PROVIDER_ENROLLMENT_REAUTH_SECONDS"),
                default=15 * 60,
                name="KOLIBRI_V3_PROVIDER_ENROLLMENT_REAUTH_SECONDS",
            ),
        )

    @classmethod
    def for_testing(
        cls,
        *,
        database_url: str | Path,
        bootstrap_owner_email: str | None = "owner@example.com",
        allowed_origins: tuple[str, ...] = ("http://testserver",),
    ) -> "Settings":
        if isinstance(database_url, Path):
            database_url = f"sqlite:///{database_url}"
        return cls(
            database_url=database_url,
            allowed_origins=allowed_origins,
            bootstrap_owner_email=bootstrap_owner_email,
            environment="test",
            cookie_secure=False,
            csrf_secret=b"kolibri-v3-test-csrf-secret-32-bytes-minimum",
            product_authority_id="authority_productdata_test001",
            product_authority_epoch=1,
            product_authority_placement_id="placement_productv3_test001",
            product_authorization_decision_id="decision_productv3_test001",
            product_authority_capabilities=(
                _PRODUCT_GOAL_INITIALIZE_CAPABILITY,
                _PRODUCT_RUN_EXECUTE_CAPABILITY,
                _PRODUCT_DEVELOPER_RUN_EXECUTE_CAPABILITY,
                _PRODUCT_PROVIDER_ENROLLMENT_CAPABILITY,
            ),
            provider_authority_dispatch_configured=True,
            fgis_pricing_enabled=True,
        )
