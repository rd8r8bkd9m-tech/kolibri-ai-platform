from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import re
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    GetJsonSchemaHandler,
    SecretStr,
    StringConstraints,
    model_validator,
)
from pydantic_core import CoreSchema


class UserRole(StrEnum):
    OWNER = "owner"
    USER = "user"


AGENT_PROFILE_ID_PATTERN = r"^[a-z0-9][a-z0-9._-]{1,95}$"
_AGENT_PROFILE_ID = re.compile(AGENT_PROFILE_ID_PATTERN)


class AgentProfile(StrEnum):
    """A bounded runtime profile ID with legacy named members.

    The three constants remain real enum members for compatibility with
    existing identity and routing code. Other registered runtime IDs are
    accepted through ``_missing_`` instead of turning this boundary into a
    closed provider enum.
    """

    AUTO = "auto"
    MIMO_CODE = "mimo-code"
    CODEX_CLI = "codex-cli"

    @classmethod
    def _missing_(cls, value: object) -> "AgentProfile | None":
        if not isinstance(value, str) or not _AGENT_PROFILE_ID.fullmatch(value):
            return None
        member = str.__new__(cls, value)
        normalized_name = value.upper().replace("-", "_").replace(".", "_")
        member._name_ = f"RUNTIME_{normalized_name}"
        member._value_ = value
        # Do not mutate Enum's process-global lookup maps. Runtime IDs are
        # validated against the live registry at the API boundary, and caching
        # arbitrary syntactically valid request values here would allow an
        # authenticated caller to grow unbounded process state.
        return member

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        _core_schema: CoreSchema,
        _handler: GetJsonSchemaHandler,
    ) -> dict[str, object]:
        return {
            "type": "string",
            "minLength": 2,
            "maxLength": 96,
            "pattern": AGENT_PROFILE_ID_PATTERN,
            "examples": ["auto", "mimo-code", "codex-cli"],
        }


DisplayName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
ModelId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$",
    ),
]
ReasoningEffort = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=32,
        pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$",
    ),
]
ServiceTier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=32,
        pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$",
    ),
]


class APIModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class RegisterRequest(APIModel):
    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=256)
    name: DisplayName


class LoginRequest(APIModel):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=256)


class MobilePlatform(StrEnum):
    IOS = "ios"
    ANDROID = "android"


DeviceName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
AppVersion = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._+()-]{0,63}$",
    ),
]


class MobileDeviceMetadata(APIModel):
    platform: MobilePlatform
    device_name: DeviceName = Field(alias="deviceName")
    app_version: AppVersion = Field(alias="appVersion")


class MobileLoginRequest(LoginRequest):
    device: MobileDeviceMetadata


class MobileRegisterRequest(RegisterRequest):
    device: MobileDeviceMetadata


class MobileRefreshRequest(APIModel):
    refresh_token: SecretStr = Field(
        min_length=32,
        max_length=512,
        alias="refreshToken",
    )


class MobileLogoutRequest(MobileRefreshRequest):
    pass


class ProfilePatch(APIModel):
    name: DisplayName | None = None
    preferred_agent_profile: AgentProfile | None = Field(
        default=None,
        alias="preferredAgentProfile",
    )

    @model_validator(mode="after")
    def require_change(self) -> "ProfilePatch":
        if self.name is None and self.preferred_agent_profile is None:
            raise ValueError("at least one profile field is required")
        return self


class AgentProfileUpdate(APIModel):
    profile: AgentProfile


class ModelSettingsUpdate(APIModel):
    profile: AgentProfile
    model: ModelId | None = None
    reasoning_effort: ReasoningEffort | None = Field(
        default=None,
        alias="reasoningEffort",
    )
    service_tier: ServiceTier | None = Field(
        default=None,
        alias="serviceTier",
    )

    @model_validator(mode="after")
    def validate_shape(self) -> "ModelSettingsUpdate":
        if self.profile is AgentProfile.AUTO:
            if self.model not in {None, "auto"}:
                raise ValueError("automatic profile cannot select a model")
            if self.reasoning_effort is not None:
                raise ValueError("automatic profile cannot select effort")
            if self.service_tier is not None:
                raise ValueError("automatic profile cannot select service tier")
            return self
        if self.model is None:
            raise ValueError("a concrete model is required")
        return self


class UserView(APIModel):
    id: str
    tenant_id: str = Field(alias="tenantId")
    email: EmailStr
    name: str
    role: UserRole
    is_platform_owner: bool = Field(alias="isPlatformOwner")
    capabilities: tuple[str, ...]
    entitlements: tuple[str, ...] = ()
    preferred_agent_profile: AgentProfile = Field(alias="preferredAgentProfile")
    preferred_model_profile: AgentProfile | None = Field(
        default=None,
        alias="preferredModelProfile",
    )
    preferred_model: str | None = Field(
        default=None,
        alias="preferredModel",
    )
    preferred_reasoning_effort: str | None = Field(
        default=None,
        alias="preferredReasoningEffort",
    )
    preferred_service_tier: str | None = Field(
        default=None,
        alias="preferredServiceTier",
    )


class SessionView(APIModel):
    authenticated: bool
    user: UserView | None


class MobileTokenView(APIModel):
    token_type: Literal["Bearer"] = Field(default="Bearer", alias="tokenType")
    access_token: str = Field(alias="accessToken")
    access_expires_at: datetime = Field(alias="accessExpiresAt")
    refresh_token: str = Field(alias="refreshToken")
    refresh_expires_at: datetime = Field(alias="refreshExpiresAt")
    device_session_id: str = Field(alias="deviceSessionId")
    user: UserView


class ProviderAdminContextView(APIModel):
    subject_id: str = Field(alias="subjectId")
    tenant_id: str = Field(alias="tenantId")
    role: Literal["superadmin"] = "superadmin"
    csrf_verified: bool = Field(alias="csrfVerified")
    expires_at: datetime = Field(alias="expiresAt")


@dataclass(frozen=True, slots=True)
class UserSession:
    user_id: str
    tenant_id: str
    role: UserRole
    preferred_agent_profile: AgentProfile
    email: str
    name: str
    preferred_model_profile: AgentProfile | None = None
    preferred_model: str | None = None
    preferred_reasoning_effort: str | None = None
    preferred_service_tier: str | None = None
    is_platform_owner: bool = False
    platform_capabilities: tuple[str, ...] = ("chat.use",)
    platform_authority_epoch: int | None = None
    product_capabilities: tuple[str, ...] = ()
    product_entitlements: tuple[str, ...] = ()
    product_entitlement_epoch: int | None = None
    expires_at: int = 0
    authenticated_at: int = 0
    session_id: str = ""
