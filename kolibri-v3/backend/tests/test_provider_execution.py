from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import hashlib
import hmac
import json
from pathlib import Path
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
    _a2a_content_hash,
    _canonical_product_request_hash,
    _generated_contracts,
    _sha256_json,
    _stable_digest,
    developer_runtime_capability,
    provider_execution_signature_payload,
    router,
)

NOW = "2026-07-26T12:00:00+03:00"
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


def test_contract_runtime_is_bundled_inside_v3() -> None:
    v3_root = Path(__file__).resolve().parents[2]
    runtime_path = Path(_generated_contracts().__file__).resolve()

    assert runtime_path.is_relative_to(v3_root)
    assert runtime_path == v3_root / "server" / "contracts_runtime.py"


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


def _local_developer_command(
    *,
    suffix: str,
    runtime_profile: str,
    trusted_binding: bool,
) -> dict[str, Any]:
    run_id = f"run_01JZPRODUCT{suffix}"
    message_id = f"message_01JZPRODUCT{suffix}"
    payload_schema_id = (
        "kolibri.product.run.execute.v1_3.command"
        if trusted_binding
        else "kolibri.product.run.execute.v1_2.command"
    )
    payload_schema_version = "1.3" if trusted_binding else "1.2"
    prompt = "Исправь ошибку и выполни тесты."
    payload: dict[str, Any] = {
        "schema_id": payload_schema_id,
        "schema_version": payload_schema_version,
        "tenant_id": "tenant_01JZPRODUCT01",
        "project_id": "project_01JZPRODUCT001",
        "thread_id": "thread_01JZPRODUCT001",
        "run_id": run_id,
        "input_message_id": message_id,
        "case_id": "case_01JZPRODUCT0001",
        "goal_id": "goal_01JZPRODUCT0001",
        "prompt": prompt,
        "prompt_hash": (
            "sha256:"
            + hashlib.sha256(prompt.encode("utf-8", "strict")).hexdigest()
        ),
        "execution_mode": "developer",
        "runtime_profile": runtime_profile,
        "model": "generic-model-01",
        "reasoning_effort": "high",
        "service_tier": "priority",
        "workspace_ref": "repository",
        "access_mode": "full",
        "sandbox": "danger-full-access",
        "approval_policy": "never",
        "reviewer": None,
        "requester_role": "owner",
    }
    if trusted_binding:
        payload.update(
            {
                "trusted_agent_profile_id": "tap_" + ("a" * 32),
                "trusted_agent_profile_epoch": 7,
                "trusted_agent_workspace_binding_id": (
                    "wsb_" + ("b" * 32)
                ),
                "trusted_agent_workspace_binding_epoch": 11,
            }
        )
    command = {
        "schema_id": "kolibri.command",
        "schema_version": "1.0",
        "message_id": f"cmd_01JZPRODUCT{suffix}",
        "command_name": "product.run.execute",
        "payload_schema_id": payload_schema_id,
        "payload_schema_version": payload_schema_version,
        "issued_at": "2026-07-26T11:59:00+03:00",
        "deadline_at": "2026-07-26T12:15:00+03:00",
        "target_owner": "logical_home_control_plane",
        "identity": {
            "tenant_id": "tenant_01JZPRODUCT01",
            "user_id": "user_01JZPRODUCT001",
            "actor": {
                "actor_type": "user",
                "actor_id": "actor_01JZPRODUCT01",
            },
            "authority": {
                "authority_id": "authority_product_data_v1",
                "authority_role": "product_data_authority",
                "authority_placement_id": "placement_product_backend",
                "authorization_decision_id": (
                    "decision_01JZPRODUCTAUTH1"
                ),
                "authority_epoch": 3,
                "capabilities": [
                    "product.developer.run.execute.request"
                ],
            },
            "subject_refs": {
                "goal_id": payload["goal_id"],
                "case_id": payload["case_id"],
                "task_id": None,
            },
        },
        "trace": {
            "trace_id": "0123456789abcdef0123456789abcdef",
            "span_id": "0123456789abcdef",
            "parent_span_id": None,
            "correlation_id": run_id,
            "causation_id": message_id,
        },
        "idempotency": {
            "key": f"product.run.execute:{run_id}",
            "scope": "aggregate",
            "scope_id": run_id,
            "canonical_request_hash": "sha256:" + ("0" * 64),
        },
        "payload": payload,
    }
    command["idempotency"]["canonical_request_hash"] = (
        _canonical_product_request_hash(command)
    )
    return command


def _local_assignment(
    *,
    assignment_id: str,
    task_id: str,
    attempt_id: str,
    lease_id: str,
    task_version: int,
    agent_card_id: str,
    agent_card_version: int,
    assignee_actor_id: str,
    temporary_role: str,
    capabilities: list[str],
    allowed_tool_ids: list[str],
    allowed_resource_refs: list[str],
    compute_units_limit: int,
    tool_calls_limit: int,
    source_command_ref: str,
    output_id: str,
    max_bytes: int,
    lease_expires_at: str,
) -> dict[str, Any]:
    return {
        "schema_id": "kolibri.agent_assignment",
        "schema_version": "1.0",
        "tenant_id": "tenant_01JZPRODUCT01",
        "assignment_id": assignment_id,
        "task_id": task_id,
        "task_version": task_version,
        "attempt_id": attempt_id,
        "goal_id": "goal_01JZPRODUCT0001",
        "case_id": "case_01JZPRODUCT0001",
        "assignee_actor_id": assignee_actor_id,
        "agent_card_id": agent_card_id,
        "agent_card_version": agent_card_version,
        "temporary_role": temporary_role,
        "purpose": (
            "Execute the owner-approved developer command stored in the "
            f"Home-owned source record {source_command_ref}; return a fenced "
            "typed A2A handoff or rejection."
            if temporary_role == "developer.runtime.executor"
            else "Issue and receive the Home-owned developer A2A request."
        ),
        "authority_profile": {
            "authority_id": "auth_01K0LHCP000001",
            "authority_role": "logical_home_control_plane",
            "authorization_decision_id": (
                "decision_" + _stable_digest(assignment_id)[:40]
            ),
            "authority_epoch": 8,
            "capabilities": capabilities,
            "allowed_tool_ids": allowed_tool_ids,
            "allowed_resource_refs": allowed_resource_refs,
            "expires_at": lease_expires_at,
        },
        "context_slice": {
            "case_version": task_version,
            "fact_ids": [],
            "decision_ids": [],
            "assumption_ids": [],
            "artifact_refs": [source_command_ref],
            "max_bytes": max_bytes,
            "classification": "restricted",
        },
        "required_output_ids": [output_id],
        "required_evidence_types": ["a2a.handoff_or_rejection"],
        "budget": {
            "compute_units_limit": compute_units_limit,
            "tool_calls_limit": tool_calls_limit,
            "external_spend_limit_minor": 0,
            "currency": "RUB",
        },
        "lease_id": lease_id,
        "deadline_at": lease_expires_at,
        "status": "active",
        "version": 1,
        "created_at": NOW,
        "updated_at": NOW,
    }


def _local_leased_task(
    *,
    command: dict[str, Any],
    card: dict[str, Any],
) -> dict[str, Any]:
    payload = command["payload"]
    trusted_binding = command["payload_schema_version"] == "1.3"
    stable = _stable_digest(command["message_id"])
    source_command_ref = "sourcecmd_" + stable[:40]
    task_id = "task_" + stable[:40]
    attempt_id = "attempt_" + _stable_digest(task_id, "attempt")[:24]
    assignment_id = (
        "assignment_" + _stable_digest(task_id, "executor")[:40]
    )
    requester_assignment_id = (
        "assignment_" + _stable_digest(task_id, "requester")[:40]
    )
    effect_id = "effect_" + _stable_digest(task_id, "effect")[:40]
    lease_id = "lease_" + _stable_digest(task_id, "lease")[:32]
    output_id = "output_" + stable[:40]
    runtime_capability = developer_runtime_capability(
        payload["runtime_profile"]
    )
    task_version = 4
    lease_expires_at = "2026-07-26T09:01:00+00:00"
    lease_until = datetime.fromisoformat(lease_expires_at).timestamp()
    trusted = (
        {
            field_name: payload[field_name]
            for field_name in (
                "trusted_agent_profile_id",
                "trusted_agent_profile_epoch",
                "trusted_agent_workspace_binding_id",
                "trusted_agent_workspace_binding_epoch",
            )
        }
        if trusted_binding
        else {}
    )
    allowed_resource_refs = sorted(
        {
            payload["goal_id"],
            payload["case_id"],
            task_id,
            source_command_ref,
            *(
                (
                    payload["trusted_agent_profile_id"],
                    payload["trusted_agent_workspace_binding_id"],
                )
                if trusted_binding
                else ()
            ),
        }
    )
    objective = (
        "Execute the owner-approved developer command stored in the "
        f"Home-owned source record {source_command_ref}; return a fenced "
        "typed A2A handoff or rejection."
    )
    task_contract = {
        "schema_id": "kolibri.task",
        "schema_version": "1.0",
        "tenant_id": payload["tenant_id"],
        "task_id": task_id,
        "goal_id": payload["goal_id"],
        "case_id": payload["case_id"],
        "title": "Выполнить developer-команду владельца",
        "objective": objective,
        "kind": "developer.runtime.execute",
        "state": "leased",
        "risk_class": "critical",
        "required_capabilities": [runtime_capability],
        "expected_outputs": [
            {
                "output_id": output_id,
                "artifact_type": "developer_execution_result",
                "schema_id": "kolibri.a2a.message_appended.event",
                "evidence_required": True,
            }
        ],
        "acceptance_criteria": [
            {
                "criterion_id": "criterion_" + stable[:40],
                "statement": (
                    "Назначенный runtime вернул типизированный A2A handoff "
                    "или rejection с тем же lease fence."
                ),
                "verification_method": (
                    "Проверка TaskAttempt, AgentAssignment, A2A cursor и "
                    "fencing token кодом Logical Home."
                ),
                "required": True,
            }
        ],
        "dependency_task_ids": [],
        "parent_task_id": None,
        "current_attempt_id": attempt_id,
        "current_assignment_id": assignment_id,
        "budget": {
            "compute_units_limit": 1_000_000,
            "tool_calls_limit": 20_000,
            "external_spend_limit_minor": 0,
            "currency": "RUB",
        },
        "deadline_at": command["deadline_at"],
        "version": task_version,
        "graph_version": 1,
        "created_at": NOW,
        "updated_at": NOW,
    }
    dispatch = {
        "schema_id": (
            "kolibri.product.developer_dispatch.v1_1"
            if trusted_binding
            else "kolibri.product.developer_dispatch"
        ),
        "schema_version": "1.1" if trusted_binding else "1.0",
        "source_command_ref": source_command_ref,
        "run_id": payload["run_id"],
        "project_id": payload["project_id"],
        "thread_id": payload["thread_id"],
        "input_message_id": payload["input_message_id"],
        "runtime_profile": payload["runtime_profile"],
        "runtime_capability": runtime_capability,
        "model": payload["model"],
        "reasoning_effort": payload["reasoning_effort"],
        "service_tier": payload["service_tier"],
        "workspace_ref": payload["workspace_ref"],
        "access_mode": payload["access_mode"],
        "sandbox": payload["sandbox"],
        "approval_policy": payload["approval_policy"],
        "reviewer": payload["reviewer"],
        **trusted,
    }
    envelope = {
        "tenant_id": payload["tenant_id"],
        "project_id": payload["project_id"],
        "thread_id": payload["thread_id"],
        "run_id": payload["run_id"],
        "input_message_id": payload["input_message_id"],
        "goal_id": payload["goal_id"],
        "case_id": payload["case_id"],
        "task_id": task_id,
        "kind": "developer.runtime.execute",
        "title": "Выполнить developer-команду владельца",
        "objective": objective,
        "required_capabilities": [runtime_capability],
        "max_retries": 0,
        "idempotency_key": (
            f"task-graph:{payload['tenant_id']}:{payload['case_id']}:"
            f"{task_id}"
        ),
        "trace_id": command["trace"]["trace_id"],
        "source": {
            "kind": (
                "product_run_execute_v1_3"
                if trusted_binding
                else "product_run_execute_v1_2"
            ),
            "message_id": command["message_id"],
            "source_command_ref": source_command_ref,
            "accepted_by": "logical_home_control_plane",
        },
        "developer_dispatch": dispatch,
        "contract_v1": task_contract,
    }
    executor_actor = (
        "agent_"
        + _stable_digest(
            card["agent_card_id"],
            card["version"],
            payload["runtime_profile"],
        )[:40]
    )
    requester_card_id = "agentcard_01K0LOGICALHOME01"
    requester_card_version = 1
    requester_actor = (
        "service_"
        + _stable_digest(
            requester_card_id,
            requester_card_version,
        )[:40]
    )
    agent_assignment = _local_assignment(
        assignment_id=assignment_id,
        task_id=task_id,
        attempt_id=attempt_id,
        lease_id=lease_id,
        task_version=task_version,
        agent_card_id=card["agent_card_id"],
        agent_card_version=card["version"],
        assignee_actor_id=executor_actor,
        temporary_role="developer.runtime.executor",
        capabilities=[
            "a2a.message.append",
            runtime_capability,
            "task_owner_state",
        ],
        allowed_tool_ids=[
            "tool.filesystem.full",
            "tool.network.full",
            "tool.shell.full",
        ],
        allowed_resource_refs=allowed_resource_refs,
        compute_units_limit=1_000_000,
        tool_calls_limit=20_000,
        source_command_ref=source_command_ref,
        output_id=output_id,
        max_bytes=512 * 1024,
        lease_expires_at=lease_expires_at,
    )
    requester_assignment = _local_assignment(
        assignment_id=requester_assignment_id,
        task_id=task_id,
        attempt_id=attempt_id,
        lease_id=lease_id,
        task_version=task_version,
        agent_card_id=requester_card_id,
        agent_card_version=requester_card_version,
        assignee_actor_id=requester_actor,
        temporary_role="developer.requester",
        capabilities=["a2a.message.append", "task_owner_state"],
        allowed_tool_ids=[],
        allowed_resource_refs=allowed_resource_refs,
        compute_units_limit=0,
        tool_calls_limit=0,
        source_command_ref=source_command_ref,
        output_id=output_id,
        max_bytes=1024 * 1024,
        lease_expires_at=lease_expires_at,
    )
    access_policy = {
        "policy_id": "developer.full_owner_approved",
        "tool_ids": [
            "tool.filesystem.full",
            "tool.network.full",
            "tool.shell.full",
        ],
        "compute_units_limit": 1_000_000,
        "tool_calls_limit": 20_000,
    }
    source_sidecar = {
        "schema_id": (
            "kolibri.product.developer_lease_source.v1_1"
            if trusted_binding
            else "kolibri.product.developer_lease_source"
        ),
        "schema_version": "1.1" if trusted_binding else "1.0",
        "source_command_ref": source_command_ref,
        "canonical_request_hash": _canonical_product_request_hash(command),
        "source_command_hash": _sha256_json(command),
        "tenant_id": payload["tenant_id"],
        "task_id": task_id,
        "task_version": task_version,
        "attempt_id": attempt_id,
        "assignment_id": assignment_id,
        "effect_id": effect_id,
        "lease_id": lease_id,
        "fencing_token": 1,
        "runtime_profile": payload["runtime_profile"],
        "access_policy": access_policy,
        **trusted,
        "source_command": command,
    }
    structured = {
        "expected_response": "a2a.handoff_or_rejection",
        "status": "requested",
        "source_command_ref": source_command_ref,
        "runtime_profile": payload["runtime_profile"],
        "model": payload["model"],
        "reasoning_effort": payload["reasoning_effort"],
        "service_tier": payload["service_tier"],
        "workspace_ref": payload["workspace_ref"],
        "access_mode": payload["access_mode"],
        "sandbox": payload["sandbox"],
        "approval_policy": payload["approval_policy"],
        "reviewer": payload["reviewer"],
        **trusted,
        "source_command_hash": _sha256_json(command),
        "canonical_request_hash": _canonical_product_request_hash(command),
        "lease": {
            "attempt_id": attempt_id,
            "lease_id": lease_id,
            "fencing_token": 1,
        },
    }
    channel_id = (
        "channel_"
        + _stable_digest(
            payload["tenant_id"],
            payload["run_id"],
            task_id,
        )[:40]
    )
    a2a_request = {
        "schema_id": "kolibri.a2a.message_appended.event",
        "schema_version": "1.0",
        "a2a_message_id": (
            "a2amsg_" + _stable_digest(channel_id, "1")[:40]
        ),
        "tenant_id": payload["tenant_id"],
        "goal_id": payload["goal_id"],
        "case_id": payload["case_id"],
        "task_id": task_id,
        "task_version": task_version,
        "channel_id": channel_id,
        "sequence": 1,
        "previous_message_id": None,
        "sender_assignment_id": requester_assignment_id,
        "sender_actor_id": requester_actor,
        "recipient_assignment_ids": [assignment_id],
        "recipient_capability": runtime_capability,
        "message_type": "request",
        "purpose": "Execute the Home-owned developer task.",
        "content": {
            "trust": "untrusted_content",
            "text": objective,
            "structured_data": structured,
            "reference_ids": sorted(
                {
                    source_command_ref,
                    task_id,
                    attempt_id,
                    *(
                        (
                            payload["trusted_agent_profile_id"],
                            payload[
                                "trusted_agent_workspace_binding_id"
                            ],
                        )
                        if trusted_binding
                        else ()
                    ),
                }
            ),
        },
        "content_hash": "sha256:" + ("0" * 64),
        "sent_at": NOW,
        "expires_at": lease_expires_at,
        "deduplication_key": (
            "a2a:developer-request:"
            + _stable_digest(payload["tenant_id"], task_id, attempt_id)
        ),
        "response_to_message_id": None,
    }
    a2a_request["content_hash"] = _a2a_content_hash(a2a_request)
    return {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "assignment_id": assignment_id,
        "effect_id": effect_id,
        "lease_id": lease_id,
        "fencing_token": 1,
        "state": "leased",
        "lease_owner": f"{CALLER_NODE_ID}:{CALLER_AGENT_ID}",
        "lease_slot_id": CALLER_SLOT_ID,
        "lease_until": lease_until,
        "kind": "developer.runtime.execute",
        "envelope": envelope,
        "agent_assignment": agent_assignment,
        "requester_assignment": requester_assignment,
        "a2a_request": a2a_request,
        "source_command_sidecar": source_sidecar,
    }


def _scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    suffix: str,
    failure: AgentRuntimeError | None = None,
    runtime_result: AgentRuntimeResult | None = None,
    trusted_binding: bool = False,
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

    del monkeypatch
    command = _local_developer_command(
        suffix=suffix,
        runtime_profile=RUNTIME_PROFILE,
        trusted_binding=trusted_binding,
    )
    card = service.catalog()["agent_cards"][0]
    leased = _local_leased_task(
        command=command,
        card=card,
    )
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
    assert f"runtime.profile:{RUNTIME_PROFILE}" in card["policy_constraints"]
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


def test_v1_3_trusted_binding_is_exact_across_a2a_and_provider_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = _scenario(
        tmp_path,
        monkeypatch,
        suffix="PEXTRUSTED01",
        trusted_binding=True,
    )
    binding = {
        "trusted_agent_profile_id": "tap_" + ("a" * 32),
        "trusted_agent_profile_epoch": 7,
        "trusted_agent_workspace_binding_id": "wsb_" + ("b" * 32),
        "trusted_agent_workspace_binding_epoch": 11,
    }
    sidecar = scenario.leased["source_command_sidecar"]
    dispatch = scenario.leased["envelope"]["developer_dispatch"]
    structured = scenario.leased["a2a_request"]["content"][
        "structured_data"
    ]

    assert scenario.command["payload_schema_version"] == "1.3"
    assert scenario.leased["envelope"]["source"]["kind"] == (
        "product_run_execute_v1_3"
    )
    assert dispatch["schema_id"] == (
        "kolibri.product.developer_dispatch.v1_1"
    )
    assert sidecar["schema_id"] == (
        "kolibri.product.developer_lease_source.v1_1"
    )
    for projection in (
        scenario.command["payload"],
        dispatch,
        sidecar,
        structured,
    ):
        assert {
            field_name: projection[field_name]
            for field_name in binding
        } == binding
    expected_refs = {
        binding["trusted_agent_profile_id"],
        binding["trusted_agent_workspace_binding_id"],
    }
    assert expected_refs.issubset(
        scenario.leased["a2a_request"]["content"]["reference_ids"]
    )
    assert expected_refs.issubset(
        scenario.leased["agent_assignment"]["authority_profile"][
            "allowed_resource_refs"
        ]
    )

    tampered_values: list[dict[str, Any]] = []
    tampered_command = copy.deepcopy(scenario.value)
    tampered_command["source_command_sidecar"]["source_command"]["payload"][
        "trusted_agent_profile_epoch"
    ] = 8
    tampered_values.append(tampered_command)
    tampered_dispatch = copy.deepcopy(scenario.value)
    tampered_dispatch["task"]["envelope"]["developer_dispatch"][
        "trusted_agent_workspace_binding_epoch"
    ] = 12
    tampered_values.append(tampered_dispatch)
    tampered_sidecar = copy.deepcopy(scenario.value)
    tampered_sidecar["source_command_sidecar"][
        "trusted_agent_profile_epoch"
    ] = 8
    tampered_values.append(tampered_sidecar)
    tampered_a2a = copy.deepcopy(scenario.value)
    tampered_a2a["a2a_request"]["content"]["structured_data"][
        "trusted_agent_workspace_binding_id"
    ] = "wsb_" + ("c" * 32)
    tampered_values.append(tampered_a2a)
    downgraded = copy.deepcopy(scenario.value)
    downgraded_source = downgraded["source_command_sidecar"][
        "source_command"
    ]
    downgraded_source["payload_schema_id"] = (
        "kolibri.product.run.execute.v1_2.command"
    )
    downgraded_source["payload_schema_version"] = "1.2"
    downgraded_source["payload"]["schema_id"] = (
        "kolibri.product.run.execute.v1_2.command"
    )
    downgraded_source["payload"]["schema_version"] = "1.2"
    tampered_values.append(downgraded)

    for value in tampered_values:
        with pytest.raises(ProviderExecutionError):
            scenario.service.execute(
                value,
                caller_node_id=CALLER_NODE_ID,
                caller_agent_id=CALLER_AGENT_ID,
            )

    completed = scenario.service.execute(
        scenario.value,
        caller_node_id=CALLER_NODE_ID,
        caller_agent_id=CALLER_AGENT_ID,
    )
    assert completed["status"] == "completed"


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
