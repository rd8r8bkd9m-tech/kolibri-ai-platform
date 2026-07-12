import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs" / "CONTROL_PLANE_AGENT_MODEL.md"
RUNNER_CONTRACT = ROOT / "docs" / "agent" / "AGENT_RUNNER_CONTRACT.md"
CONTROL_SCHEMA = ROOT / "contracts" / "kolibri-os-v1" / "control-plane.schema.json"
OPENAPI = ROOT / "contracts" / "kolibri-os-v1" / "openapi.json"


def test_agent_model_separates_compatibility_from_required_target() -> None:
    text = DOCUMENT.read_text(encoding="utf-8")

    for required in (
        "control-plane/home",
        "Current compatibility versus required target",
        "single-slot compatibility worker",
        "scalar `active_task`",
        "Redis compatibility state",
        "PostgreSQL Program Ledger",
        "NATS JetStream",
        "authority_epoch",
        "active_attempts",
        "content-addressed storage",
        "does not yet persist or validate `authority_epoch`",
    ):
        assert required in text

    for stale in (
        "Desired Calibri V1 Endpoint Shape",
        "Map current Fabric routes into this shape gradually",
        "Task Registry / Redis State / Logs / Artifacts / Approvals",
    ):
        assert stale not in text


def test_agent_model_matches_runner_and_machine_contracts() -> None:
    text = DOCUMENT.read_text(encoding="utf-8")
    runner = RUNNER_CONTRACT.read_text(encoding="utf-8")
    schema = json.loads(CONTROL_SCHEMA.read_text(encoding="utf-8"))
    openapi = json.loads(OPENAPI.read_text(encoding="utf-8"))

    assert schema["x-kolibri-authority"] == "control-plane/home"
    assert {"main", "primary", "primary-candidate"}.issubset(
        schema["x-kolibri-forbidden-authority-identities"]
    )
    assert {
        "Task",
        "TaskAttempt",
        "LeaseFencing",
        "TaskCompletionEvidence",
        "TaskCompletionVerifier",
    }.issubset(schema["$defs"])

    expected_implementation = {
        ("/v1/tasks", "get"): "compatibility",
        ("/v1/tasks", "post"): "compatibility",
        ("/v1/tasks/{task_id}/events", "get"): "target",
        ("/v1/tasks/{task_id}/events", "post"): "target",
        ("/v1/runtime/actors", "get"): "compatibility",
        ("/v1/runtime/summary", "get"): "compatibility",
        ("/v1/runtime/dags", "get"): "target",
        ("/v1/runtime/pools", "get"): "target",
    }
    for (path, method), status in expected_implementation.items():
        assert openapi["paths"][path][method]["x-kolibri-implementation"] == status
        assert f"`{status}`" in text

    for binding in (
        "attempt_id",
        "lease_owner",
        "lease_until",
        "fencing_token",
        "max_attempts",
        "kolibri.task-completion-evidence.v1",
        "kolibri.task-completion-binding.v1",
        "kolibri.control-plane-completion-verifier.v1",
    ):
        assert binding in text
        assert binding in runner


def test_agent_model_requires_api_only_workers_and_fresh_21_node_proof() -> None:
    text = DOCUMENT.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    for required in (
        "SSH is operator-only",
        "never worker transport",
        "Provider selection is independent of task authority",
        "A provider failure can change the provider route, but it cannot change the Control Plane",
        "The public model identity remains `kolibri`",
        "The requested provider is honored exactly",
        "the meaning of 21/21",
        "canonical signed mesh manifest",
        "Home-issued attempt and positive fence",
        "passed independent verifier bound to the same attempt",
        "Membership or heartbeat proves neither provider execution nor task completion",
        "Mac is an optional Apple/provider worker",
    ):
        assert required in normalized

    assert "It does not claim that a strict Home canary" in normalized
    assert "Do not claim operational readiness from documentation or source code" in normalized
