import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "contracts" / "kolibri-os-v1"


def load_json(name: str):
    return json.loads((CONTRACT_ROOT / name).read_text(encoding="utf-8"))


def test_domain_schema_has_durable_swarm_canvas_and_learning_boundaries():
    schema = load_json("domain.schema.json")
    definitions = schema["$defs"]

    assert schema["$schema"].endswith("2020-12/schema")
    assert {
        "Event",
        "ContextPack",
        "SwarmPlan",
        "PlanNode",
        "LogicalActor",
        "Artifact",
        "Canvas",
        "Automation",
        "LearningCandidate",
    }.issubset(definitions)

    task_states = set(definitions["PlanNode"]["properties"]["state"]["enum"])
    assert {"ready", "leased", "running", "review", "retry", "completed", "dead"}.issubset(task_states)
    assert definitions["SwarmPlan"]["allOf"][1]["properties"]["max_logical_actors"]["maximum"] >= 1000

    learning = definitions["LearningCandidate"]["allOf"][1]
    assert {"consent", "license", "sanitization", "quality_verdict", "promotion_status"}.issubset(learning["required"])
    assert "negative" in learning["properties"]["license"]["enum"]
    assert "denied" in learning["properties"]["consent"]["enum"]


def test_openapi_freezes_unified_surface_and_single_public_model():
    contract = load_json("openapi.json")
    paths = contract["paths"]
    required = {
        "/v1/responses",
        "/v1/resume",
        "/v1/projects",
        "/v1/plans",
        "/v1/tasks",
        "/v1/runtime/actors",
        "/v1/runtime/summary",
        "/v1/artifacts",
        "/v1/canvases",
        "/v1/previews",
        "/v1/browser-sessions",
        "/v1/estimates",
        "/v1/documents",
        "/v1/builds",
        "/v1/automations",
    }
    assert required.issubset(paths)
    assert paths["/v1/models"]["get"]["x-kolibri-public-model"] == "kolibri"
    assert paths["/v1/runtime/summary"]["get"]["x-kolibri-rule"].startswith("real telemetry")


def test_contract_freeze_separates_bootstrap_connectivity_from_execution_truth():
    text = (ROOT / "docs" / "KOLIBRI_OS_V1_CONTRACT_FREEZE.md").read_text(encoding="utf-8")
    assert "known-good Mac-to-fleet bootstrap" in text
    assert "real capability execution" in text
    assert "A heartbeat, accepted HTTP request or provider response alone is not proof" in text
