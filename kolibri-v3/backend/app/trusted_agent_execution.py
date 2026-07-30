"""Frozen trusted-agent profile binding for Product Chat execution.

The control-plane profile is optional for compatibility with runs accepted
before the trusted-agent rollout.  Once an active singleton profile exists,
new developer runs must match it exactly and freeze its profile/workspace
epochs.  Every execution boundary revalidates that frozen tuple against live
authority so revoke and profile updates take effect without rewriting a run.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3


_CAPABILITIES = ["developer.runtime.execute"]
_TOOL_POLICY_ID = "developer.full.v1"


class TrustedAgentExecutionError(Exception):
    """A public-safe failure of trusted-agent execution authority."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class TrustedAgentExecutionBinding:
    profile_id: str
    profile_epoch: int
    workspace_binding_id: str
    workspace_binding_epoch: int


def _profile_row(
    database: sqlite3.Connection,
    *,
    profile_id: str | None = None,
) -> sqlite3.Row | None:
    profile_filter = (
        "profile.id = ?"
        if profile_id is not None
        else (
            "profile.authority_id = 'platform_owner' "
            "AND profile.lifecycle_status = 'active'"
        )
    )
    parameters: tuple[object, ...] = (
        (profile_id,) if profile_id is not None else ()
    )
    return database.execute(
        f"""
        SELECT
            profile.*,
            binding.owner_user_id AS binding_owner_user_id,
            binding.owner_tenant_id AS binding_owner_tenant_id,
            binding.authority_epoch AS binding_authority_epoch,
            binding.lifecycle_status AS binding_lifecycle_status,
            binding.workspace_epoch AS live_workspace_binding_epoch,
            authority.active AS authority_active,
            authority.authority_epoch AS live_authority_epoch,
            authority.capabilities_json AS authority_capabilities_json
        FROM trusted_agent_profiles AS profile
        JOIN trusted_agent_workspace_bindings AS binding
          ON binding.id = profile.workspace_binding_id
        JOIN platform_authority_grants AS authority
          ON authority.authority_id = profile.authority_id
         AND authority.user_id = profile.owner_user_id
         AND authority.tenant_id = profile.owner_tenant_id
        WHERE {profile_filter}
        ORDER BY profile.created_at DESC, profile.id DESC
        LIMIT 1
        """,
        parameters,
    ).fetchone()


def _authority_capabilities(row: sqlite3.Row) -> set[str]:
    try:
        value = json.loads(str(row["authority_capabilities_json"]))
    except (TypeError, ValueError) as exc:
        raise TrustedAgentExecutionError(
            "trusted_agent_authority_invalid",
            "Trusted-agent authority is invalid.",
        ) from exc
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise TrustedAgentExecutionError(
            "trusted_agent_authority_invalid",
            "Trusted-agent authority is invalid.",
        )
    return set(value)


def _validate_live_row(
    row: sqlite3.Row,
    *,
    tenant_id: str,
    user_id: str,
    authority_epoch: int,
    runtime_profile: str,
    access_mode: str,
    sandbox_profile: str,
    approval_policy: str,
    approvals_reviewer: str | None,
    expected: TrustedAgentExecutionBinding | None,
) -> TrustedAgentExecutionBinding:
    if (
        str(row["owner_user_id"]) != user_id
        or str(row["owner_tenant_id"]) != tenant_id
        or str(row["binding_owner_user_id"]) != user_id
        or str(row["binding_owner_tenant_id"]) != tenant_id
        or int(row["authority_epoch"]) != authority_epoch
        or int(row["binding_authority_epoch"]) != authority_epoch
        or int(row["live_authority_epoch"]) != authority_epoch
        or int(row["authority_active"]) != 1
        or "chat.developer.request" not in _authority_capabilities(row)
    ):
        raise TrustedAgentExecutionError(
            "trusted_agent_authority_changed",
            "Trusted-agent owner authority changed.",
        )
    if (
        str(row["lifecycle_status"]) != "active"
        or (
            expected is not None
            and int(row["profile_epoch"]) != expected.profile_epoch
        )
    ):
        raise TrustedAgentExecutionError(
            "trusted_agent_profile_changed",
            "Trusted-agent profile changed or was revoked.",
        )
    if (
        str(row["binding_lifecycle_status"]) != "active"
        or int(row["workspace_binding_epoch"])
        != int(row["live_workspace_binding_epoch"])
        or (
            expected is not None
            and (
                str(row["workspace_binding_id"])
                != expected.workspace_binding_id
                or int(row["workspace_binding_epoch"])
                != expected.workspace_binding_epoch
            )
        )
    ):
        raise TrustedAgentExecutionError(
            "trusted_agent_workspace_changed",
            "Trusted-agent workspace binding changed or was revoked.",
        )
    try:
        capabilities = json.loads(str(row["capabilities_json"]))
    except (TypeError, ValueError) as exc:
        raise TrustedAgentExecutionError(
            "trusted_agent_profile_invalid",
            "Trusted-agent profile is invalid.",
        ) from exc
    if (
        capabilities != _CAPABILITIES
        or str(row["tool_policy_id"]) != _TOOL_POLICY_ID
        or int(row["max_concurrency"]) != 1
        or str(row["runtime_profile"]) != runtime_profile
        or str(row["access_mode"]) != access_mode
        or str(row["sandbox_profile"]) != sandbox_profile
        or str(row["approval_policy"]) != approval_policy
        or row["approvals_reviewer"] != approvals_reviewer
    ):
        raise TrustedAgentExecutionError(
            "trusted_agent_profile_selection_mismatch",
            "Selected developer runtime does not match the trusted profile.",
        )
    binding = TrustedAgentExecutionBinding(
        profile_id=str(row["id"]),
        profile_epoch=int(row["profile_epoch"]),
        workspace_binding_id=str(row["workspace_binding_id"]),
        workspace_binding_epoch=int(row["workspace_binding_epoch"]),
    )
    if expected is not None and binding != expected:
        raise TrustedAgentExecutionError(
            "trusted_agent_profile_changed",
            "Trusted-agent profile changed or was revoked.",
        )
    return binding


def select_trusted_agent_execution_binding(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str,
    authority_epoch: int,
    runtime_profile: str,
    access_mode: str,
    sandbox_profile: str,
    approval_policy: str,
    approvals_reviewer: str | None,
) -> TrustedAgentExecutionBinding | None:
    """Select the active singleton profile, if this deployment configured one."""

    row = _profile_row(database)
    if row is None:
        return None
    return _validate_live_row(
        row,
        tenant_id=tenant_id,
        user_id=user_id,
        authority_epoch=authority_epoch,
        runtime_profile=runtime_profile,
        access_mode=access_mode,
        sandbox_profile=sandbox_profile,
        approval_policy=approval_policy,
        approvals_reviewer=approvals_reviewer,
        expected=None,
    )


def validate_frozen_trusted_agent_execution_binding(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str,
    authority_epoch: int,
    runtime_profile: str,
    access_mode: str,
    sandbox_profile: str,
    approval_policy: str,
    approvals_reviewer: str | None,
    profile_id: object,
    profile_epoch: object,
    workspace_binding_id: object,
    workspace_binding_epoch: object,
) -> TrustedAgentExecutionBinding | None:
    """Revalidate a frozen profile tuple immediately before an effect."""

    values = (
        profile_id,
        profile_epoch,
        workspace_binding_id,
        workspace_binding_epoch,
    )
    if all(value is None for value in values):
        # Compatibility for runs accepted before migration 036 or before an
        # owner configured the optional trusted-agent control profile.
        return None
    if (
        not isinstance(profile_id, str)
        or not profile_id
        or not isinstance(profile_epoch, int)
        or profile_epoch < 1
        or not isinstance(workspace_binding_id, str)
        or not workspace_binding_id
        or not isinstance(workspace_binding_epoch, int)
        or workspace_binding_epoch < 1
    ):
        raise TrustedAgentExecutionError(
            "trusted_agent_execution_binding_invalid",
            "Frozen trusted-agent execution binding is invalid.",
        )
    expected = TrustedAgentExecutionBinding(
        profile_id=profile_id,
        profile_epoch=profile_epoch,
        workspace_binding_id=workspace_binding_id,
        workspace_binding_epoch=workspace_binding_epoch,
    )
    row = _profile_row(database, profile_id=profile_id)
    if row is None:
        raise TrustedAgentExecutionError(
            "trusted_agent_profile_changed",
            "Trusted-agent profile changed or was revoked.",
        )
    return _validate_live_row(
        row,
        tenant_id=tenant_id,
        user_id=user_id,
        authority_epoch=authority_epoch,
        runtime_profile=runtime_profile,
        access_mode=access_mode,
        sandbox_profile=sandbox_profile,
        approval_policy=approval_policy,
        approvals_reviewer=approvals_reviewer,
        expected=expected,
    )


__all__ = [
    "TrustedAgentExecutionBinding",
    "TrustedAgentExecutionError",
    "select_trusted_agent_execution_binding",
    "validate_frozen_trusted_agent_execution_binding",
]
