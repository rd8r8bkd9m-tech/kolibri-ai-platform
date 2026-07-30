"""Strict public contracts for the R1 owner trusted-agent control plane."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from .schemas import APIModel


WorkspaceBindingId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^wsb_[0-9a-f]{32}$",
    ),
]
WorkspaceServerRef = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^wsref_[0-9a-f]{32}$",
    ),
]
TrustedAgentProfileId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^tap_[0-9a-f]{32}$",
    ),
]
FingerprintToken = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^sha256:[0-9a-f]{64}$",
    ),
]
RuntimeProfileId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=2,
        max_length=96,
        pattern=r"^[a-z0-9][a-z0-9._-]{1,95}$",
    ),
]
AgentCardId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$",
    ),
]
WorkspaceEnvironment = Literal["development", "staging", "production"]
LifecycleStatus = Literal["active", "revoked"]
AuditTargetType = Literal["binding", "profile"]
AuditAction = Literal[
    "binding.created",
    "binding.updated",
    "binding.revoked",
    "profile.created",
    "profile.updated",
    "profile.revoked",
    "profile.revoked_by_binding",
]

_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def _reject_path_like_label(value: str) -> str:
    """Human labels may not become a covert filesystem/URI input channel."""

    if (
        "/" in value
        or "\\" in value
        or "://" in value
        or value.startswith("~")
        or _WINDOWS_PATH.match(value) is not None
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("display name must not contain a path or URI")
    return value


class WorkspaceBindingCreate(APIModel):
    environment: WorkspaceEnvironment
    fingerprint_token: FingerprintToken = Field(alias="fingerprintToken")


class WorkspaceBindingPatch(APIModel):
    revision: Annotated[int, Field(ge=1)]
    environment: WorkspaceEnvironment | None = None
    fingerprint_token: FingerprintToken | None = Field(
        default=None,
        alias="fingerprintToken",
    )

    @model_validator(mode="after")
    def require_change(self) -> "WorkspaceBindingPatch":
        if not (self.model_fields_set - {"revision"}):
            raise ValueError("at least one binding field is required")
        return self


class RevisionRevoke(APIModel):
    revision: Annotated[int, Field(ge=1)]


class WorkspaceBindingView(APIModel):
    id: WorkspaceBindingId
    server_ref: WorkspaceServerRef = Field(alias="serverRef")
    environment: WorkspaceEnvironment
    fingerprint_token: FingerprintToken = Field(alias="fingerprintToken")
    authority_epoch: Annotated[int, Field(ge=1)] = Field(
        alias="authorityEpoch",
    )
    lifecycle_status: LifecycleStatus = Field(alias="lifecycleStatus")
    workspace_epoch: Annotated[int, Field(ge=1)] = Field(
        alias="workspaceEpoch",
    )
    revision: Annotated[int, Field(ge=1)]
    created_at: Annotated[int, Field(ge=0)] = Field(alias="createdAt")
    updated_at: Annotated[int, Field(ge=0)] = Field(alias="updatedAt")
    revoked_at: Annotated[int, Field(ge=0)] | None = Field(
        default=None,
        alias="revokedAt",
    )


class WorkspaceBindingPage(APIModel):
    items: list[WorkspaceBindingView]
    next_cursor: WorkspaceBindingId | None = Field(
        default=None,
        alias="nextCursor",
    )


class TrustedAgentProfileCreate(APIModel):
    workspace_binding_id: WorkspaceBindingId = Field(alias="workspaceBindingId")
    display_name: Annotated[str, Field(min_length=1, max_length=120)] = Field(
        alias="displayName",
    )
    runtime_profile: RuntimeProfileId = Field(alias="runtimeProfile")
    agent_card_id: AgentCardId = Field(alias="agentCardId")
    agent_card_version: Annotated[int, Field(ge=1, le=2_147_483_647)] = Field(
        alias="agentCardVersion",
    )
    access_mode: Literal["full"] = Field(default="full", alias="accessMode")
    sandbox_profile: Literal["danger-full-access"] = Field(
        default="danger-full-access",
        alias="sandboxProfile",
    )
    approval_policy: Literal["never"] = Field(
        default="never",
        alias="approvalPolicy",
    )
    max_concurrency: Literal[1] = Field(default=1, alias="maxConcurrency")

    @field_validator("display_name")
    @classmethod
    def display_name_is_not_a_path(cls, value: str) -> str:
        return _reject_path_like_label(value)


class TrustedAgentProfilePatch(APIModel):
    revision: Annotated[int, Field(ge=1)]
    display_name: Annotated[str, Field(min_length=1, max_length=120)] | None = (
        Field(default=None, alias="displayName")
    )
    runtime_profile: RuntimeProfileId | None = Field(
        default=None,
        alias="runtimeProfile",
    )
    agent_card_id: AgentCardId | None = Field(
        default=None,
        alias="agentCardId",
    )
    agent_card_version: Annotated[
        int,
        Field(ge=1, le=2_147_483_647),
    ] | None = Field(default=None, alias="agentCardVersion")

    @field_validator("display_name")
    @classmethod
    def display_name_is_not_a_path(cls, value: str | None) -> str | None:
        return None if value is None else _reject_path_like_label(value)

    @model_validator(mode="after")
    def require_change(self) -> "TrustedAgentProfilePatch":
        if not (self.model_fields_set - {"revision"}):
            raise ValueError("at least one profile field is required")
        return self


class TrustedAgentProfileView(APIModel):
    id: TrustedAgentProfileId
    workspace_binding_id: WorkspaceBindingId = Field(alias="workspaceBindingId")
    workspace_binding_epoch: Annotated[int, Field(ge=1)] = Field(
        alias="workspaceBindingEpoch",
    )
    display_name: str = Field(alias="displayName")
    runtime_profile: RuntimeProfileId = Field(alias="runtimeProfile")
    agent_card_id: AgentCardId = Field(alias="agentCardId")
    agent_card_version: Annotated[int, Field(ge=1)] = Field(
        alias="agentCardVersion",
    )
    capabilities: list[Literal["developer.runtime.execute"]]
    tool_policy_id: Literal["developer.full.v1"] = Field(alias="toolPolicyId")
    access_mode: Literal["full"] = Field(alias="accessMode")
    sandbox_profile: Literal["danger-full-access"] = Field(
        alias="sandboxProfile",
    )
    approval_policy: Literal["never"] = Field(alias="approvalPolicy")
    approvals_reviewer: None = Field(default=None, alias="approvalsReviewer")
    max_concurrency: Literal[1] = Field(alias="maxConcurrency")
    authority_epoch: Annotated[int, Field(ge=1)] = Field(
        alias="authorityEpoch",
    )
    lifecycle_status: LifecycleStatus = Field(alias="lifecycleStatus")
    profile_epoch: Annotated[int, Field(ge=1)] = Field(alias="profileEpoch")
    revision: Annotated[int, Field(ge=1)]
    created_at: Annotated[int, Field(ge=0)] = Field(alias="createdAt")
    updated_at: Annotated[int, Field(ge=0)] = Field(alias="updatedAt")
    revoked_at: Annotated[int, Field(ge=0)] | None = Field(
        default=None,
        alias="revokedAt",
    )


class TrustedAgentProfilePage(APIModel):
    items: list[TrustedAgentProfileView]
    next_cursor: TrustedAgentProfileId | None = Field(
        default=None,
        alias="nextCursor",
    )


class TrustedAgentAuditView(APIModel):
    id: Annotated[
        str,
        StringConstraints(pattern=r"^taudit_[0-9a-f]{32}$"),
    ]
    action: AuditAction
    target_type: AuditTargetType = Field(alias="targetType")
    target_id: str = Field(alias="targetId")
    target_revision: Annotated[int, Field(ge=1)] = Field(
        alias="targetRevision",
    )
    target_epoch: Annotated[int, Field(ge=1)] = Field(alias="targetEpoch")
    authority_epoch: Annotated[int, Field(ge=1)] = Field(
        alias="authorityEpoch",
    )
    before: dict[str, Any]
    after: dict[str, Any]
    created_at: Annotated[int, Field(ge=0)] = Field(alias="createdAt")


class TrustedAgentAuditPage(APIModel):
    items: list[TrustedAgentAuditView]
    next_cursor: str | None = Field(default=None, alias="nextCursor")
