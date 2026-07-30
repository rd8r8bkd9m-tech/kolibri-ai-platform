from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.home_runtime import (
    HomeRuntimeCommandError,
    HomeRuntimeStatusError,
    _validate_product_command,
    _validate_product_payload,
    validate_product_execution_status,
)
from app.chat.service import build_product_run_command
from app.chat.errors import ChatRuntimeUnavailableError
from app.config import Settings
from app.schemas import AgentProfile, UserRole, UserSession


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
V1_1_EXAMPLE = (
    REPOSITORY_ROOT
    / "contracts/v1/product/examples/valid-run-execute-command-v1.1.json"
)
V1_2_EXAMPLE = (
    REPOSITORY_ROOT
    / "contracts/v1/product/examples/valid-run-execute-command-v1.2.json"
)
V1_3_EXAMPLE = (
    REPOSITORY_ROOT
    / "contracts/v1/product/examples/valid-run-execute-command-v1.3.json"
)
STATUS_V1_0_EXAMPLE = (
    REPOSITORY_ROOT
    / "contracts/v1/product/examples/valid-run-execution-status.json"
)
STATUS_V1_1_EXAMPLE = (
    REPOSITORY_ROOT
    / "contracts/v1/product/examples/valid-run-execution-status-v1.1.json"
)


def _v1_1_payload() -> dict[str, object]:
    return json.loads(V1_1_EXAMPLE.read_text(encoding="utf-8"))


def _fixture(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _developer_command(
    tmp_path: Path,
    *,
    trusted_binding: bool = False,
) -> dict[str, object]:
    payload = _fixture(
        V1_3_EXAMPLE if trusted_binding else V1_2_EXAMPLE
    )
    identity = UserSession(
        user_id="user_01J000000000000000000000000",
        tenant_id="tenant_01J00000000000000000000000",
        role=UserRole.OWNER,
        preferred_agent_profile=AgentProfile.AUTO,
        email="owner@example.com",
        name="Owner",
        is_platform_owner=True,
        platform_capabilities=(
            "platform.admin",
            "chat.developer.request",
            "chat.use",
        ),
    )
    return build_product_run_command(
        settings=Settings.for_testing(database_url=tmp_path / "runtime.db"),
        identity=identity,
        project_id=str(payload["project_id"]),
        thread_id=str(payload["thread_id"]),
        run_id=str(payload["run_id"]),
        input_message_id=str(payload["input_message_id"]),
        goal_id=str(payload["goal_id"]),
        case_id=str(payload["case_id"]),
        prompt=str(payload["prompt"]),
        created_at="2026-07-29T12:00:00+00:00",
        selected_profile=str(payload["runtime_profile"]),
        selected_model=str(payload["model"]),
        selected_reasoning_effort=str(payload["reasoning_effort"]),
        selected_service_tier=str(payload["service_tier"]),
        execution_mode="developer",
        workspace_ref=str(payload["workspace_ref"]),
        access_mode=str(payload["access_mode"]),
        sandbox=str(payload["sandbox"]),
        approval_policy=str(payload["approval_policy"]),
        reviewer=None,
        **(
            {
                "trusted_agent_profile_id": str(
                    payload["trusted_agent_profile_id"]
                ),
                "trusted_agent_profile_epoch": int(
                    payload["trusted_agent_profile_epoch"]
                ),
                "trusted_agent_workspace_binding_id": str(
                    payload["trusted_agent_workspace_binding_id"]
                ),
                "trusted_agent_workspace_binding_epoch": int(
                    payload["trusted_agent_workspace_binding_epoch"]
                ),
            }
            if trusted_binding
            else {}
        ),
    )


def test_v1_0_product_payload_remains_accepted_without_model_fields() -> None:
    payload = _v1_1_payload()
    payload["schema_id"] = "kolibri.product.run.execute.command"
    payload["schema_version"] = "1.0"
    del payload["preferred_model"]
    del payload["preferred_reasoning_effort"]

    _validate_product_payload(payload)


@pytest.mark.parametrize(
    ("model", "effort"),
    (
        ("gpt-5.6-sol", "high"),
        (None, None),
    ),
)
def test_v1_1_product_payload_accepts_complete_model_effort_pairs(
    model: str | None,
    effort: str | None,
) -> None:
    payload = _v1_1_payload()
    payload["preferred_model"] = model
    payload["preferred_reasoning_effort"] = effort

    _validate_product_payload(copy.deepcopy(payload))


@pytest.mark.parametrize(
    ("model", "effort"),
    (
        ("gpt-5.6-sol", None),
        (None, "high"),
    ),
)
def test_v1_1_product_payload_rejects_partial_model_effort_pairs(
    model: str | None,
    effort: str | None,
) -> None:
    payload = _v1_1_payload()
    payload["preferred_model"] = model
    payload["preferred_reasoning_effort"] = effort

    with pytest.raises(HomeRuntimeCommandError) as exc_info:
        _validate_product_payload(payload)

    assert exc_info.value.code == "home_product_command_payload_invalid"


def test_v1_2_developer_payload_accepts_an_opaque_runtime_profile() -> None:
    payload = _fixture(V1_2_EXAMPLE)
    payload["runtime_profile"] = "future-agent-runtime-2040"
    payload["model"] = None
    payload["reasoning_effort"] = None
    payload["service_tier"] = None

    _validate_product_payload(payload)


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("execution_mode", "standard"),
        ("requester_role", "user"),
        ("runtime_profile", "bad profile"),
        ("access_mode", "unbounded"),
    ),
)
def test_v1_2_developer_payload_rejects_invalid_generic_fields(
    field_name: str,
    value: object,
) -> None:
    payload = _fixture(V1_2_EXAMPLE)
    payload[field_name] = value

    with pytest.raises(HomeRuntimeCommandError) as exc_info:
        _validate_product_payload(payload)

    assert exc_info.value.code == "home_product_command_payload_invalid"


def test_v1_2_full_command_requires_developer_capability(
    tmp_path: Path,
) -> None:
    command = _developer_command(tmp_path)
    _validate_product_command(command)

    capabilities = command["identity"]["authority"]["capabilities"]
    capabilities.remove("product.developer.run.execute.request")
    with pytest.raises(HomeRuntimeCommandError) as exc_info:
        _validate_product_command(command)

    assert exc_info.value.code == "home_product_command_authority_invalid"


def test_v1_3_command_freezes_complete_trusted_binding_and_never_downgrades(
    tmp_path: Path,
) -> None:
    command = _developer_command(tmp_path, trusted_binding=True)
    payload = command["payload"]
    expected_binding = {
        "trusted_agent_profile_id": "tap_" + ("a" * 32),
        "trusted_agent_profile_epoch": 7,
        "trusted_agent_workspace_binding_id": "wsb_" + ("b" * 32),
        "trusted_agent_workspace_binding_epoch": 11,
    }

    assert command["payload_schema_id"] == (
        "kolibri.product.run.execute.v1_3.command"
    )
    assert command["payload_schema_version"] == "1.3"
    assert {
        field_name: payload[field_name]
        for field_name in expected_binding
    } == expected_binding
    _validate_product_command(command)

    downgraded = copy.deepcopy(command)
    downgraded["payload_schema_id"] = (
        "kolibri.product.run.execute.v1_2.command"
    )
    downgraded["payload_schema_version"] = "1.2"
    downgraded["payload"]["schema_id"] = (
        "kolibri.product.run.execute.v1_2.command"
    )
    downgraded["payload"]["schema_version"] = "1.2"
    with pytest.raises(HomeRuntimeCommandError):
        _validate_product_command(downgraded)


def test_developer_command_rejects_partial_trusted_binding(
    tmp_path: Path,
) -> None:
    legacy = _fixture(V1_2_EXAMPLE)
    identity = UserSession(
        user_id="user_01J000000000000000000000000",
        tenant_id="tenant_01J00000000000000000000000",
        role=UserRole.OWNER,
        preferred_agent_profile=AgentProfile.AUTO,
        email="owner@example.com",
        name="Owner",
        is_platform_owner=True,
        platform_capabilities=(
            "platform.admin",
            "chat.developer.request",
            "chat.use",
        ),
    )

    with pytest.raises(ChatRuntimeUnavailableError):
        build_product_run_command(
            settings=Settings.for_testing(
                database_url=tmp_path / "runtime.db"
            ),
            identity=identity,
            project_id=str(legacy["project_id"]),
            thread_id=str(legacy["thread_id"]),
            run_id=str(legacy["run_id"]),
            input_message_id=str(legacy["input_message_id"]),
            goal_id=str(legacy["goal_id"]),
            case_id=str(legacy["case_id"]),
            prompt=str(legacy["prompt"]),
            created_at="2026-07-29T12:00:00+00:00",
            selected_profile=str(legacy["runtime_profile"]),
            selected_model=str(legacy["model"]),
            selected_reasoning_effort=str(
                legacy["reasoning_effort"]
            ),
            selected_service_tier=str(legacy["service_tier"]),
            execution_mode="developer",
            workspace_ref=str(legacy["workspace_ref"]),
            access_mode=str(legacy["access_mode"]),
            sandbox=str(legacy["sandbox"]),
            approval_policy=str(legacy["approval_policy"]),
            reviewer=None,
            trusted_agent_profile_id="tap_" + ("a" * 32),
        )


def test_v1_2_command_accepts_only_universal_status_v1_1(
    tmp_path: Path,
) -> None:
    command = _developer_command(tmp_path)
    status = _fixture(STATUS_V1_1_EXAMPLE)
    status["runtime_profile"] = command["payload"]["runtime_profile"]
    status["run_id"] = command["payload"]["run_id"]
    status["result_hash"] = (
        "sha256:848f1b11ff8fb215948369540b123532ee795fb52a014b78e"
        "575c9c2c3b9312a"
    )
    status["evidence"]["content_hash"] = status["result_hash"]

    accepted = validate_product_execution_status(status, command)
    assert accepted == status

    with pytest.raises(HomeRuntimeStatusError):
        validate_product_execution_status(
            _fixture(STATUS_V1_0_EXAMPLE),
            command,
        )


def test_legacy_command_does_not_reinterpret_universal_status() -> None:
    payload = _v1_1_payload()
    command = {
        "payload_schema_id": payload["schema_id"],
        "payload_schema_version": payload["schema_version"],
        "payload": payload,
    }

    with pytest.raises(HomeRuntimeStatusError):
        validate_product_execution_status(
            _fixture(STATUS_V1_1_EXAMPLE),
            command,
        )
