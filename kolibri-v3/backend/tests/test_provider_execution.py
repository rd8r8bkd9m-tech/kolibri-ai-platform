from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import hashlib
import hmac
import json
from pathlib import Path
import sys
import threading
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent_runtime import (
    AgentRuntimeCapabilities,
    AgentRuntimeDescriptor,
    AgentRuntimeError,
    AgentRuntimeRegistry,
    AgentRuntimeRequest,
    AgentRuntimeResult,
    AgentToolCall,
    DelegatingAgentRuntime,
)
from app.config import Settings
from app.database import connect_database, initialize_database
from app.provider_execution import (
    PROVIDER_EXECUTION_PATH,
    PROVIDER_EXECUTION_REQUEST_SCHEMA_ID,
    PROVIDER_EXECUTION_SCHEMA_VERSION,
    ProviderExecutionError,
    ProviderExecutionSecurity,
    ProviderExecutionService,
    developer_runtime_capability,
    provider_execution_signature_payload,
    router,
)


ROOT = Path(__file__).resolve().parents[3]
ROOT_TESTS = ROOT / "tests"
if str(ROOT_TESTS) not in sys.path:
    sys.path.insert(0, str(ROOT_TESTS))

from test_factory_control_product_developer_dispatch import (  # noqa: E402
    NOW,
    admit,
    configure_control,
    developer_command,
    lease,
    register_requester_card,
)


RUNTIME_PROFILE = "third-agent.runtime-01"
CALLER_NODE_ID = "node-third-runtime"
CALLER_AGENT_ID = "agent-third-runtime"
CALLER_SLOT_ID = "slot-third-runtime"
SECRET = b"provider-execution-test-token-0123456789abcdef"


@dataclass(slots=True)
class ProviderScenario:
    settings: Settings
    registry: AgentRuntimeRegistry
    service: ProviderExecutionService
    requests: list[AgentRuntimeRequest]
    command: dict[str, Any]
    leased: dict[str, Any]
    value: dict[str, Any]


def _runtime(
    profile_id: str,
    *,
    requests: list[AgentRuntimeRequest],
    workspace: Path,
    failure: AgentRuntimeError | None = None,
    runtime_result: AgentRuntimeResult | None = None,
) -> DelegatingAgentRuntime:
    descriptor = AgentRuntimeDescriptor(
        profile_id=profile_id,
        runtime_id=f"{profile_id}-engine",
        display_name=f"Runtime {profile_id}",
        capabilities=AgentRuntimeCapabilities(
            modes=frozenset({"developer"}),
            streaming=False,
            structured_output=False,
            activity_events=True,
            persistent_sessions=True,
        ),
    )

    def execute(request: AgentRuntimeRequest) -> AgentRuntimeResult:
        requests.append(request)
        assert request.on_activity is not None
        request.on_activity(
            "repository.read",
            {
                "path": str(workspace / "src" / "service.py"),
                "outside_path": "/etc/private-provider-config",
                "authorization": "Bearer secret-provider-token",
            },
        )
        if failure is not None:
            raise failure
        return runtime_result or AgentRuntimeResult(
            text="Third runtime completed the requested verification.",
            session_id="session_third_runtime_01",
        )

    return DelegatingAgentRuntime(
        descriptor=descriptor,
        execute=execute,
    )


def _settings(database_path: Path, workspace: Path) -> Settings:
    return replace(
        Settings.for_testing(database_url=database_path),
        provider_execution_enabled=True,
        provider_execution_workspace_root=workspace,
        provider_execution_workspace_ref="repository",
        provider_execution_allowed_node_id=CALLER_NODE_ID,
        provider_execution_allowed_agent_id=CALLER_AGENT_ID,
        provider_execution_allowed_slot_id=CALLER_SLOT_ID,
        provider_execution_card_updated_at=NOW,
        provider_execution_timeout_seconds=120,
    )


def _scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    suffix: str,
    failure: AgentRuntimeError | None = None,
    runtime_result: AgentRuntimeResult | None = None,
) -> ProviderScenario:
    database_path = tmp_path / f"{suffix.lower()}.db"
    settings = _settings(database_path, tmp_path)
    initialize_database(settings.database_url)
    requests: list[AgentRuntimeRequest] = []
    registry = AgentRuntimeRegistry()
    registry.register(
        _runtime(
            RUNTIME_PROFILE,
            requests=requests,
            workspace=tmp_path,
            failure=failure,
            runtime_result=runtime_result,
        )
    )
    now = datetime.fromisoformat(NOW)
    service = ProviderExecutionService(
        settings=settings,
        runtime_registry=registry,
        now=lambda: now,
    )

    control, _store = configure_control(
        monkeypatch,
        f"factory_control_provider_execution_{suffix.lower()}",
    )
    command = developer_command(
        control,
        suffix=suffix,
        runtime_profile=RUNTIME_PROFILE,
    )
    command["payload"]["workspace_ref"] = "repository"
    command["idempotency"]["canonical_request_hash"] = (
        control.canonical_request_hash(command)
    )
    register_requester_card(control)
    card = service.catalog()["agent_cards"][0]
    control.save_a2a_agent_card(
        control.parse_declared_a2a_agent_card_v1(card)
    )

    status_code, accepted = admit(control, command)
    assert status_code == 202
    task = control.load_task(accepted["execution_id"])
    assert task is not None
    leased = lease(control, task)
    assert leased is not None
    value = {
        "schema_id": PROVIDER_EXECUTION_REQUEST_SCHEMA_ID,
        "schema_version": PROVIDER_EXECUTION_SCHEMA_VERSION,
        "effect_key": leased["effect_id"],
        "task": leased,
        "agent_assignment": leased["agent_assignment"],
        "requester_assignment": leased["requester_assignment"],
        "a2a_request": leased["a2a_request"],
        "source_command_sidecar": leased["source_command_sidecar"],
    }
    return ProviderScenario(
        settings=settings,
        registry=registry,
        service=service,
        requests=requests,
        command=command,
        leased=leased,
        value=value,
    )


def _signed_headers(
    *,
    body: bytes = b"",
    method: str = "GET",
    nonce: str,
    signature_secret: bytes = SECRET,
) -> dict[str, str]:
    timestamp = str(int(datetime.fromisoformat(NOW).timestamp()))
    body_sha256 = hashlib.sha256(body).hexdigest()
    signature = hmac.new(
        signature_secret,
        provider_execution_signature_payload(
            method=method,
            logical_path=PROVIDER_EXECUTION_PATH,
            timestamp=timestamp,
            nonce=nonce,
            node_id=CALLER_NODE_ID,
            agent_id=CALLER_AGENT_ID,
            body_sha256=body_sha256,
        ),
        hashlib.sha256,
    ).hexdigest()
    return {
        "Authorization": f"Bearer {SECRET.decode('ascii')}",
        "X-Kolibri-Timestamp": timestamp,
        "X-Kolibri-Nonce": nonce,
        "X-Kolibri-Node-Id": CALLER_NODE_ID,
        "X-Kolibri-Agent-Id": CALLER_AGENT_ID,
        "X-Kolibri-Body-SHA256": body_sha256,
        "X-Kolibri-Signature": signature,
    }


def test_third_runtime_catalog_and_exact_frozen_execution_replay_after_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = _scenario(
        tmp_path,
        monkeypatch,
        suffix="PEXSUCCESS01",
    )

    catalog = scenario.service.catalog()
    assert catalog["schema_id"] == "kolibri.provider_execution.catalog"
    assert len(catalog["agent_cards"]) == 1
    card = catalog["agent_cards"][0]
    capability = developer_runtime_capability(RUNTIME_PROFILE)
    assert card["availability"] == "available"
    assert capability in card["capabilities"]
    assert card["agent_card_id"] == (
        scenario.leased["agent_assignment"]["agent_card_id"]
    )
    assert card["version"] == (
        scenario.leased["agent_assignment"]["agent_card_version"]
    )
    assert scenario.value["source_command_sidecar"] == (
        scenario.leased["source_command_sidecar"]
    )
    assert scenario.value["source_command_sidecar"]["source_command"] == (
        scenario.command
    )

    completed = scenario.service.execute(
        scenario.value,
        caller_node_id=CALLER_NODE_ID,
        caller_agent_id=CALLER_AGENT_ID,
    )

    assert completed["status"] == "completed"
    assert completed["replayed"] is False
    assert completed["runtime_profile"] == RUNTIME_PROFILE
    assert completed["output"] == {
        "response": "Third runtime completed the requested verification.",
        "session_id": "session_third_runtime_01",
        "tool_call": None,
    }
    assert len(scenario.requests) == 1
    runtime_request = scenario.requests[0]
    assert runtime_request.messages[-1].content == (
        scenario.command["payload"]["prompt"]
    )
    assert runtime_request.configuration.selection.model_id == (
        "generic-model-01"
    )
    assert runtime_request.configuration.selection.reasoning_effort == "high"
    assert runtime_request.configuration.selection.service_tier == "priority"
    assert runtime_request.configuration.selection.explicit_profile is True
    assert runtime_request.configuration.workspace.reference == "repository"
    assert runtime_request.configuration.workspace.root == tmp_path.resolve()
    assert runtime_request.configuration.access.mode == "full"
    assert runtime_request.configuration.access.sandbox == (
        "danger-full-access"
    )
    assert runtime_request.configuration.access.approval_policy == "never"
    assert runtime_request.configuration.access.approvals_reviewer is None
    activity_text = json.dumps(completed["activity"])
    assert "secret-provider-token" not in activity_text
    assert "/etc/private-provider-config" not in activity_text
    assert "[REDACTED]" in activity_text
    assert "[outside-workspace]" in activity_text

    restarted = ProviderExecutionService(
        settings=scenario.settings,
        runtime_registry=scenario.registry,
        now=lambda: datetime.fromisoformat(NOW),
    )
    replay = restarted.execute(
        scenario.value,
        caller_node_id=CALLER_NODE_ID,
        caller_agent_id=CALLER_AGENT_ID,
    )
    assert replay == {**completed, "replayed": True}
    assert len(scenario.requests) == 1


def test_missing_selected_profile_never_substitutes_another_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = _scenario(
        tmp_path,
        monkeypatch,
        suffix="PEXNOFALLBACK01",
    )
    fallback_requests: list[AgentRuntimeRequest] = []
    fallback_registry = AgentRuntimeRegistry()
    fallback_registry.register(
        _runtime(
            "healthy-alternative.runtime-02",
            requests=fallback_requests,
            workspace=tmp_path,
        )
    )
    service = ProviderExecutionService(
        settings=scenario.settings,
        runtime_registry=fallback_registry,
        now=lambda: datetime.fromisoformat(NOW),
    )

    with pytest.raises(ProviderExecutionError) as error:
        service.execute(
            scenario.value,
            caller_node_id=CALLER_NODE_ID,
            caller_agent_id=CALLER_AGENT_ID,
        )

    assert error.value.code == "provider_execution_runtime_unavailable"
    assert fallback_requests == []
    assert scenario.requests == []


def test_oversized_prompt_is_rejected_before_runtime_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = _scenario(
        tmp_path,
        monkeypatch,
        suffix="PEXOVERSIZED01",
    )
    tampered = copy.deepcopy(scenario.value)
    prompt = "x" * 200_001
    command = tampered["source_command_sidecar"]["source_command"]
    command["payload"]["prompt"] = prompt
    command["payload"]["prompt_hash"] = (
        "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    )

    with pytest.raises(ProviderExecutionError) as error:
        scenario.service.execute(
            tampered,
            caller_node_id=CALLER_NODE_ID,
            caller_agent_id=CALLER_AGENT_ID,
        )

    assert error.value.code == "provider_execution_contract_invalid"
    assert scenario.requests == []


def test_access_and_assignment_tool_mismatches_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = _scenario(
        tmp_path,
        monkeypatch,
        suffix="PEXACCESS01",
    )
    access_tampered = copy.deepcopy(scenario.value)
    access_tampered["source_command_sidecar"]["source_command"]["payload"][
        "sandbox"
    ] = "workspace-write"
    with pytest.raises(ProviderExecutionError) as access_error:
        scenario.service.execute(
            access_tampered,
            caller_node_id=CALLER_NODE_ID,
            caller_agent_id=CALLER_AGENT_ID,
        )
    assert access_error.value.code == (
        "provider_execution_access_policy_invalid"
    )

    assignment_tampered = copy.deepcopy(scenario.value)
    assignment_tampered["agent_assignment"]["authority_profile"][
        "allowed_tool_ids"
    ] = ["tool.shell.full"]
    with pytest.raises(ProviderExecutionError) as assignment_error:
        scenario.service.execute(
            assignment_tampered,
            caller_node_id=CALLER_NODE_ID,
            caller_agent_id=CALLER_AGENT_ID,
        )
    assert assignment_error.value.code == (
        "provider_execution_assignment_binding_mismatch"
    )
    assert scenario.requests == []


def test_stale_fencing_projection_is_rejected_before_runtime_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = _scenario(
        tmp_path,
        monkeypatch,
        suffix="PEXSTALEFENCE01",
    )
    stale = copy.deepcopy(scenario.value)
    stale["task"]["fencing_token"] += 1

    with pytest.raises(ProviderExecutionError) as error:
        scenario.service.execute(
            stale,
            caller_node_id=CALLER_NODE_ID,
            caller_agent_id=CALLER_AGENT_ID,
        )

    assert error.value.code == "provider_execution_source_sidecar_mismatch"
    assert scenario.requests == []


def test_server_tool_allowlist_cannot_expand_frozen_assignment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = _scenario(
        tmp_path,
        monkeypatch,
        suffix="PEXTOOLPOLICY01",
    )
    restricted_settings = replace(
        scenario.settings,
        provider_execution_allowed_tool_ids=("tool.shell.full",),
    )
    service = ProviderExecutionService(
        settings=restricted_settings,
        runtime_registry=scenario.registry,
        now=lambda: datetime.fromisoformat(NOW),
    )

    with pytest.raises(ProviderExecutionError) as error:
        service.execute(
            scenario.value,
            caller_node_id=CALLER_NODE_ID,
            caller_agent_id=CALLER_AGENT_ID,
        )

    assert error.value.code == "provider_execution_tool_not_allowed"
    assert scenario.requests == []


def test_provider_error_is_safe_and_durably_replayed_without_second_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = AgentRuntimeError(
        "third_runtime_temporarily_unavailable",
        "Bearer secret-provider-token must never leave the runtime.",
        category="unavailable",
        retryable=True,
    )
    scenario = _scenario(
        tmp_path,
        monkeypatch,
        suffix="PEXFAILURE01",
        failure=failure,
    )

    failed = scenario.service.execute(
        scenario.value,
        caller_node_id=CALLER_NODE_ID,
        caller_agent_id=CALLER_AGENT_ID,
    )

    assert failed["status"] == "failed"
    assert failed["replayed"] is False
    assert failed["output"] is None
    assert failed["error"] == {
        "code": "third_runtime_temporarily_unavailable",
        "category": "unavailable",
        "retryable": True,
        "safe_message": "The selected runtime could not complete the task.",
    }
    assert "secret-provider-token" not in json.dumps(failed)
    assert len(scenario.requests) == 1

    restarted = ProviderExecutionService(
        settings=scenario.settings,
        runtime_registry=scenario.registry,
        now=lambda: datetime.fromisoformat(NOW),
    )
    replay = restarted.execute(
        scenario.value,
        caller_node_id=CALLER_NODE_ID,
        caller_agent_id=CALLER_AGENT_ID,
    )
    assert replay == {**failed, "replayed": True}
    assert len(scenario.requests) == 1


def test_terminal_replay_rejects_every_changed_durable_lease_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = _scenario(
        tmp_path,
        monkeypatch,
        suffix="PEXREPLAYBIND01",
    )
    completed = scenario.service.execute(
        scenario.value,
        caller_node_id=CALLER_NODE_ID,
        caller_agent_id=CALLER_AGENT_ID,
    )
    assert completed["status"] == "completed"
    assert len(scenario.requests) == 1

    replacements: dict[str, Any] = {
        "effect_hash": "sha256:" + ("f" * 64),
        "runtime_profile": "other.runtime-02",
        "task_id": "task_changed_binding",
        "attempt_id": "attempt_changed_binding",
        "assignment_id": "assignment_changed_binding",
        "lease_id": "lease_changed_binding",
        "fencing_token": scenario.leased["fencing_token"] + 1,
        "slot_id": "slot-changed-binding",
    }
    database = connect_database(scenario.settings.database_url)
    try:
        original = database.execute(
            """
            SELECT *
            FROM provider_execution_effects
            WHERE tenant_id = ? AND effect_key = ?
            """,
            (
                scenario.command["payload"]["tenant_id"],
                scenario.value["effect_key"],
            ),
        ).fetchone()
        assert original is not None
        for field, replacement in replacements.items():
            database.execute(
                f"""
                UPDATE provider_execution_effects
                SET {field} = ?
                WHERE tenant_id = ? AND effect_key = ?
                """,
                (
                    replacement,
                    scenario.command["payload"]["tenant_id"],
                    scenario.value["effect_key"],
                ),
            )
            with pytest.raises(ProviderExecutionError) as error:
                scenario.service.execute(
                    scenario.value,
                    caller_node_id=CALLER_NODE_ID,
                    caller_agent_id=CALLER_AGENT_ID,
                )
            assert error.value.code == (
                "provider_execution_idempotency_conflict"
            )
            database.execute(
                f"""
                UPDATE provider_execution_effects
                SET {field} = ?
                WHERE tenant_id = ? AND effect_key = ?
                """,
                (
                    original[field],
                    scenario.command["payload"]["tenant_id"],
                    scenario.value["effect_key"],
                ),
            )
    finally:
        database.close()
    assert len(scenario.requests) == 1


def test_interrupted_execution_reconciles_after_durable_heartbeat_expiry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = _scenario(
        tmp_path,
        monkeypatch,
        suffix="PEXRECOVER01",
    )
    execution = scenario.service._validate(
        scenario.value,
        caller_node_id=CALLER_NODE_ID,
        caller_agent_id=CALLER_AGENT_ID,
    )
    reserved, existing = scenario.service.journal.reserve(
        execution,
        owner_id=scenario.service.execution_owner_id,
        now=datetime.fromisoformat(NOW),
    )
    assert reserved is True
    assert existing is None

    with pytest.raises(ProviderExecutionError) as in_progress:
        scenario.service.execute(
            scenario.value,
            caller_node_id=CALLER_NODE_ID,
            caller_agent_id=CALLER_AGENT_ID,
        )
    assert in_progress.value.code == "provider_execution_effect_in_progress"

    recovered_at = datetime.fromisoformat(NOW) + timedelta(
        seconds=31
    )
    restarted = ProviderExecutionService(
        settings=scenario.settings,
        runtime_registry=scenario.registry,
        now=lambda: recovered_at,
    )
    replay = restarted.execute(
        scenario.value,
        caller_node_id=CALLER_NODE_ID,
        caller_agent_id=CALLER_AGENT_ID,
    )
    assert replay["status"] == "failed"
    assert replay["replayed"] is True
    assert replay["error"]["code"] == "provider_execution_interrupted"
    assert scenario.requests == []


def test_advertised_single_slot_capacity_is_durably_enforced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _scenario(
        tmp_path,
        monkeypatch,
        suffix="PEXCAPACITY01",
    )
    second = _scenario(
        tmp_path,
        monkeypatch,
        suffix="PEXCAPACITY02",
    )
    entered = threading.Event()
    release = threading.Event()
    outcomes: list[dict[str, Any]] = []
    runtime = first.registry.require(RUNTIME_PROFILE)

    def blocking_execute(request: AgentRuntimeRequest) -> AgentRuntimeResult:
        first.requests.append(request)
        entered.set()
        assert release.wait(timeout=5)
        return AgentRuntimeResult(text="first execution completed")

    runtime._execute = blocking_execute

    worker = threading.Thread(
        target=lambda: outcomes.append(
            first.service.execute(
                first.value,
                caller_node_id=CALLER_NODE_ID,
                caller_agent_id=CALLER_AGENT_ID,
            )
        )
    )
    worker.start()
    assert entered.wait(timeout=5)
    try:
        with pytest.raises(ProviderExecutionError) as capacity_error:
            first.service.execute(
                second.value,
                caller_node_id=CALLER_NODE_ID,
                caller_agent_id=CALLER_AGENT_ID,
            )
        assert capacity_error.value.code == (
            "provider_execution_capacity_exhausted"
        )
    finally:
        release.set()
        worker.join(timeout=5)
    assert not worker.is_alive()
    assert outcomes[0]["status"] == "completed"
    assert len(first.requests) == 1


@pytest.mark.parametrize(
    "runtime_result",
    [
        AgentRuntimeResult(text="😀" * 200_000),
        AgentRuntimeResult(
            tool_call=AgentToolCall(
                name="repository.write",
                arguments={
                    f"field_{index}": ["x" * 4_000] * 64
                    for index in range(64)
                },
            )
        ),
    ],
)
def test_oversized_runtime_result_is_failed_before_terminal_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runtime_result: AgentRuntimeResult,
) -> None:
    scenario = _scenario(
        tmp_path,
        monkeypatch,
        suffix=(
            "PEXRESULTTEXT01"
            if runtime_result.text is not None
            else "PEXRESULTTOOL01"
        ),
        runtime_result=runtime_result,
    )
    failed = scenario.service.execute(
        scenario.value,
        caller_node_id=CALLER_NODE_ID,
        caller_agent_id=CALLER_AGENT_ID,
    )
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "provider_execution_result_too_large"
    assert (
        len(
            json.dumps(
                failed,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        <= 512 * 1024
    )

    replay = scenario.service.execute(
        scenario.value,
        caller_node_id=CALLER_NODE_ID,
        caller_agent_id=CALLER_AGENT_ID,
    )
    assert replay == {**failed, "replayed": True}
    assert len(scenario.requests) == 1


def test_endpoint_requires_loopback_bound_hmac_and_rejects_oversized_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = _scenario(
        tmp_path,
        monkeypatch,
        suffix="PEXENDPOINT01",
    )
    now_timestamp = datetime.fromisoformat(NOW).timestamp()
    security = ProviderExecutionSecurity(
        secret=SECRET,
        allowed_node_id=CALLER_NODE_ID,
        allowed_agent_id=CALLER_AGENT_ID,
        now=lambda: now_timestamp,
    )
    application = FastAPI()
    application.include_router(router)
    application.state.agent_runtime_registry = scenario.registry
    application.state.provider_execution_service = scenario.service
    application.state.provider_execution_security = security

    with TestClient(
        application,
        client=("203.0.113.9", 49000),
    ) as remote_client:
        remote = remote_client.get(
            PROVIDER_EXECUTION_PATH,
            headers=_signed_headers(nonce="nonce-endpoint-remote-0001"),
        )
    assert remote.status_code == 403
    assert remote.json()["code"] == "provider_execution_loopback_required"

    with TestClient(
        application,
        client=("127.0.0.1", 49001),
    ) as local_client:
        invalid = local_client.get(
            PROVIDER_EXECUTION_PATH,
            headers=_signed_headers(
                nonce="nonce-endpoint-invalid-0001",
                signature_secret=b"different-signature-secret-0123456789",
            ),
        )
        assert invalid.status_code == 401
        assert invalid.json()["code"] == "provider_execution_auth_invalid"

        headers = _signed_headers(nonce="nonce-endpoint-valid-000001")
        accepted = local_client.get(
            PROVIDER_EXECUTION_PATH,
            headers=headers,
        )
        assert accepted.status_code == 200
        assert accepted.json() == scenario.service.catalog()

        replay = local_client.get(
            PROVIDER_EXECUTION_PATH,
            headers=headers,
        )
        assert replay.status_code == 409
        assert replay.json()["code"] == "provider_execution_auth_replay"

        oversized = local_client.post(
            PROVIDER_EXECUTION_PATH,
            content=b"x" * ((512 * 1024) + 1),
        )
        assert oversized.status_code == 413
        assert oversized.json()["code"] == (
            "provider_execution_request_too_large"
        )
