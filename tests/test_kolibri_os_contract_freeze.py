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
        "/v1/approvals/{approval_id}",
        "/v1/releases/{release_id}/nodes/{node_id}/health",
    }
    assert required.issubset(paths)
    assert paths["/v1/models"]["get"]["x-kolibri-public-model"] == "kolibri"
    assert paths["/v1/runtime/summary"]["get"]["x-kolibri-rule"].startswith("real telemetry")
    assert paths["/v1/approvals"]["post"]["x-kolibri-authority"] == "owner sshsig required"
    assert paths["/v1/releases/{release_id}/nodes/{node_id}/health"]["get"]["x-kolibri-truth-rule"].startswith("derived only")


def test_contract_freeze_separates_bootstrap_connectivity_from_execution_truth():
    text = (ROOT / "docs" / "KOLIBRI_OS_V1_CONTRACT_FREEZE.md").read_text(encoding="utf-8")
    assert "known-good Mac-to-fleet bootstrap" in text
    assert "real capability execution" in text
    assert "A heartbeat, accepted HTTP request or provider response alone is not proof" in text


def test_native_tool_contract_separates_skills_and_requires_live_jsonl_probe():
    contract = load_json("openapi.json")
    definitions = load_json("domain.schema.json")["$defs"]
    tool_rule = contract["paths"]["/v1/tools"]["get"]["x-kolibri-truth-rule"]
    assert "native tools only" in tool_rule
    assert "NativeToolRuntimeProbe" in definitions

    registry = json.loads((ROOT / "backend" / "kolibri-tools.json").read_text(encoding="utf-8"))
    tools = {item["id"]: item for item in registry["tools"]}
    assert set(tools) == {"tool:code_inspection", "tool:web_search"}
    assert tools["tool:code_inspection"]["requires_event_probe"] is True
    assert tools["tool:web_search"]["requires_event_probe"] is False
    assert tools["tool:web_search"]["execution_backend"] == "controlled_http_gateway"
    assert tools["tool:web_search"]["policy_version"] == "kolibri.web-search-policy.v1"
    assert "web_search_preview" in tools["tool:web_search"]["aliases"]
    assert "command_execution" in tools["tool:code_inspection"]["event_aliases"]
    assert "web_search" in tools["tool:web_search"]["event_aliases"]
