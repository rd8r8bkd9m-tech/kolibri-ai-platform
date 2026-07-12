from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "contracts" / "kolibri-os-v1"


def load_json(name: str):
    return json.loads((CONTRACT_ROOT / name).read_text(encoding="utf-8"))


def load_control():
    path = ROOT / "ops" / "factory_control.py"
    spec = importlib.util.spec_from_file_location("machine_contract_factory_control", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_home_control_plane_schema_matches_live_runtime_constants():
    control = load_control()
    schema = load_json("control-plane.schema.json")
    definitions = schema["$defs"]

    assert schema["x-kolibri-authority"] == "control-plane/home"
    assert schema["x-kolibri-authority-mode"] == "single-fail-closed"
    assert set(schema["x-kolibri-forbidden-authority-identities"]) == {
        "main",
        "primary",
        "primary-candidate",
    }
    assert set(definitions["TaskState"]["enum"]) == {
        control.STATE_QUEUED,
        control.STATE_LEASED,
        control.STATE_RUNNING,
        control.STATE_WAITING_REVIEW,
        control.STATE_REVIEW,
        control.STATE_COMPLETED,
        control.STATE_FAILED,
        control.STATE_CANCELLED,
        control.STATE_RETRY,
        control.STATE_DEAD,
    }
    assert definitions["Task"]["properties"]["lease_fencing_schema"]["const"] == control.LEASE_FENCING_SCHEMA
    assert definitions["TaskCompletionEvidence"]["properties"]["schema_version"]["const"] == control.COMPLETION_EVIDENCE_SCHEMA
    assert definitions["TaskCompletionVerifier"]["properties"]["schema_version"]["const"] == control.COMPLETION_VERIFIER_SCHEMA
    assert definitions["TaskCompletionVerifier"]["properties"]["verifier"]["const"] == "control-plane/home"
    assert definitions["TaskCompletionVerifier"]["properties"]["independent"]["const"] is True
    assert "required_capability" in definitions["TaskCreateRequest"]["properties"]
    assert "required_capabilities" not in definitions["TaskCreateRequest"]["properties"]


def test_openapi_binds_only_live_task_and_node_mutations_to_strict_schemas():
    openapi = load_json("openapi.json")
    paths = openapi["paths"]
    control_source = (ROOT / "ops" / "factory_control.py").read_text(encoding="utf-8")
    host_source = (ROOT / "ops" / "agent_host.py").read_text(encoding="utf-8")
    live_operations = {
        ("/v1/tasks", "post"): "TaskCreate",
        ("/v1/tasks/lease", "post"): "TaskLease",
        ("/v1/tasks/{task_id}/heartbeat", "post"): "TaskHeartbeat",
        ("/v1/tasks/{task_id}/complete", "post"): "TaskComplete",
        ("/v1/tasks/{task_id}/fail", "post"): "TaskFail",
        ("/v1/tasks/{task_id}/cancel", "post"): "TaskCancel",
        ("/v1/nodes/register", "post"): "NodeRegister",
        ("/v1/nodes/{node_id}/heartbeat", "post"): "NodeHeartbeat",
    }

    assert openapi["x-kolibri-authority"] == "control-plane/home"
    assert openapi["x-kolibri-control-plane-contract"] == "./control-plane.schema.json"
    for (path, method), request_body in live_operations.items():
        operation = paths[path][method]
        assert operation["x-kolibri-implementation"] == "compatibility"
        assert "home" in operation["x-kolibri-authority"]
        assert operation["requestBody"]["$ref"].endswith(request_body)

    for runtime_path in (
        "/v1/tasks/lease",
        "/v1/tasks/",
        "/v1/nodes/register",
        "/v1/nodes/",
    ):
        assert runtime_path in control_source
    for runtime_path in (
        "/v1/tasks/lease",
        "/heartbeat",
        "/complete",
        "/fail",
        "/v1/nodes/register",
    ):
        assert runtime_path in host_source

    for operation in paths["/v1/tasks/{task_id}/events"].values():
        assert operation["x-kolibri-implementation"] == "target"
        assert operation["x-planned"] is True


def test_attempt_fence_and_completion_contract_is_fail_closed():
    definitions = load_json("control-plane.schema.json")["$defs"]
    lease_required = set(definitions["LeaseFencing"]["required"])
    assert lease_required == {"attempt_id", "fencing_token", "node_id", "agent_id"}
    assert definitions["LeaseFencing"]["properties"]["fencing_token"]["minimum"] == 1

    completion = definitions["TaskCompletionRequest"]["allOf"][1]
    assert set(completion["required"]) == {"result_reference", "result"}
    assert {"status", "fencing_token"} <= set(completion["properties"]["result"]["required"])

    checks = definitions["CompletionChecks"]
    assert "fencing_token" in checks["required"]
    assert "binding_sha256" in checks["required"]
    rejected = definitions["LeaseFenceRejected"]["properties"]["reason"]["enum"]
    assert {"attempt_id_mismatch", "fencing_token_missing", "fencing_token_mismatch", "lease_node_mismatch", "lease_agent_mismatch"} <= set(rejected)


def test_worker_card_availability_is_not_execution_proof():
    definitions = load_json("control-plane.schema.json")["$defs"]
    observation = definitions["CapabilityObservation"]
    assert set(observation["required"]) == {
        "capability",
        "declared",
        "probe_status",
        "execution_proof",
    }
    assert definitions["CapabilityExecutionProof"]["properties"]["state"]["enum"] == [
        "not_run",
        "failed",
        "verified",
    ]
    active = definitions["NodeRecord"]["properties"]["active_attempts"]
    assert "null" in active["type"]
    assert "unknown" in active["x-kolibri-null-means"]
    heartbeat_rule = definitions["NodeHeartbeatRequest"]["x-kolibri-truth-rule"]
    assert "not invocation proof" in heartbeat_rule
    assert "stale" in definitions["NodeRecord"]["properties"]["health"]["enum"]
    assert {"$ref": "#/$defs/Timestamp"} in definitions["NodeRecord"]["properties"]["heartbeat_at"]["anyOf"]
    assert {"type": "null"} in definitions["NodeRecord"]["properties"]["heartbeat_at"]["anyOf"]
    log_paths = definitions["TaskHeartbeatRequest"]["allOf"][1]["properties"]["log_paths"]
    assert "object" in log_paths["type"]
    assert log_paths["additionalProperties"] == {"type": "string"}


def test_openapi_machine_refs_resolve_to_tracked_contract_definitions():
    openapi = load_json("openapi.json")
    external = load_json("control-plane.schema.json")

    for schema in openapi["components"]["schemas"].values():
        reference = schema.get("$ref")
        if not reference or not reference.startswith("./control-plane.schema.json#/$defs/"):
            continue
        definition = reference.rsplit("/", 1)[-1]
        assert definition in external["$defs"]
