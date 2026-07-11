import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from capability_gateway import CapabilityGateway, CapabilityRequestError  # noqa: E402


def executable(path: Path, body: str = "exit 0\n") -> str:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def test_skill_probe_reads_frontmatter_only_and_requires_real_runner(tmp_path, monkeypatch):
    skill = tmp_path / "skills" / "safe-skill" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    # Invalid UTF-8 and a secret-like value after the closing marker prove the
    # probe does not read or expose the skill body.
    skill.write_bytes(
        b"---\nname: safe-skill\ndescription: Safe metadata\n---\n"
        b"body-secret-sk-never-read-123456789\xff\xfe"
    )
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", executable(tmp_path / "codex"))

    gateway = CapabilityGateway([tmp_path / "skills"], cache_ttl=0, include_packaged_registry=False)
    envelope = gateway.envelope(refresh=True)

    record = next(item for item in envelope["data"] if item["id"] == "skill:safe-skill")
    assert record["status"] == "available"
    assert record["source"]["type"] == "codex_skill_frontmatter"
    assert "body-secret" not in json.dumps(envelope)
    assert gateway.envelope(tools_only=True)["data"] == []
    with pytest.raises(CapabilityRequestError, match="requested_capability_is_not_native_tool"):
        gateway.validate_requested_tools([{"type": "skill", "name": "safe-skill"}])
    assert gateway.plan_skills("Use the safe-skill skill for this task")[0]["id"] == "skill:safe-skill"


def test_missing_runner_is_truthfully_unavailable_and_rejected(tmp_path, monkeypatch):
    skill = tmp_path / "SKILL.md"
    skill.write_text("---\nname: offline-skill\ndescription: Installed only\n---\nbody", encoding="utf-8")
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", str(tmp_path / "missing-codex"))
    gateway = CapabilityGateway([skill], cache_ttl=0, include_packaged_registry=False)

    record = gateway.envelope(refresh=True)["data"][0]
    assert record["status"] == "unavailable"
    assert record["availability_reason"] == "required_runner_missing"
    with pytest.raises(CapabilityRequestError, match="requested_capability_is_not_native_tool"):
        gateway.validate_requested_tools([{"id": "skill:offline-skill"}])


def test_plugin_connector_declaration_is_degraded_until_runtime_verified(tmp_path, monkeypatch):
    plugin = tmp_path / "demo" / ".codex-plugin" / "plugin.json"
    plugin.parent.mkdir(parents=True)
    plugin.write_text(json.dumps({
        "name": "demo", "description": "Demo connector", "mcpServers": "./.mcp.json",
    }), encoding="utf-8")
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", executable(tmp_path / "codex"))
    gateway = CapabilityGateway([tmp_path], cache_ttl=0, include_packaged_registry=False)

    tools = gateway.envelope(tools_only=True, refresh=True)
    connector = next(item for item in tools["data"] if item["id"] == "tool:demo:mcp")
    assert connector["status"] == "degraded"
    with pytest.raises(CapabilityRequestError) as exc:
        gateway.validate_requested_tools([{"id": "tool:demo:mcp"}])
    assert exc.value.status == "degraded"


def test_explicit_runtime_tool_manifest_can_make_tool_available(tmp_path, monkeypatch):
    manifest = tmp_path / "kolibri-tools.json"
    manifest.write_text(json.dumps({
        "tools": [{
            "id": "tool:search", "name": "search", "kind": "tool",
            "status": "available", "providers": ["codex"], "aliases": ["web_search"],
        }]
    }), encoding="utf-8")
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", executable(tmp_path / "codex"))
    gateway = CapabilityGateway([manifest], cache_ttl=0, include_packaged_registry=False)

    tools = gateway.envelope(tools_only=True, refresh=True)
    assert tools["status"] == "available"
    assert tools["data"][0]["id"] == "tool:search"
    assert gateway.validate_requested_tools([{"type": "web_search"}])[0]["id"] == "tool:search"


def test_recursive_probe_never_opens_generic_tools_json(tmp_path, monkeypatch):
    generic = tmp_path / "plugin" / "tools.json"
    generic.parent.mkdir(parents=True)
    generic.write_bytes(b"not capability metadata \xff\xfe secret")
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", executable(tmp_path / "codex"))

    envelope = CapabilityGateway([tmp_path], cache_ttl=0, include_packaged_registry=False).envelope(refresh=True)
    assert envelope["data"] == []
    assert "runtime_capability_manifest_invalid" not in json.dumps(envelope)


def test_packaged_tools_distinguish_native_runner_probe_from_controlled_gateway(tmp_path, monkeypatch):
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", executable(tmp_path / "codex"))
    gateway = CapabilityGateway([], cache_ttl=60)
    tools = gateway.envelope(tools_only=True)
    assert {item["id"] for item in tools["data"]} == {
        "tool:code_inspection", "tool:project_knowledge", "tool:web_search",
    }
    by_id = {item["id"]: item for item in tools["data"]}
    assert by_id["tool:code_inspection"]["status"] == "degraded"
    assert by_id["tool:web_search"]["status"] == "available"
    assert by_id["tool:project_knowledge"]["status"] == "available"
    with pytest.raises(CapabilityRequestError, match="requested_tool_not_available"):
        gateway.validate_requested_tools([{"type": "code_inspection"}])
    assert gateway.validate_requested_tools([{"type": "web_search"}])[0]["id"] == "tool:web_search"
    assert gateway.validate_requested_tools([{"type": "project_knowledge"}])[0]["id"] == "tool:project_knowledge"


def test_packaged_native_tool_live_probe_promotes_only_verified_events(tmp_path, monkeypatch):
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", executable(tmp_path / "codex"))

    def verified_probe(record):
        event_type = "command_execution" if record["id"] == "tool:code_inspection" else "web_search"
        tool_name = "shell" if record["id"] == "tool:code_inspection" else "web_search"
        return {
            "status": "available", "reason": "native_jsonl_event_verified",
            "observed_event_types": [event_type], "observed_tool_names": [tool_name],
            "tool_event_count": 1, "verifier_verdict": "passed",
            "evidence_binding_sha256": "d" * 64, "error_types": [],
        }

    gateway = CapabilityGateway([], cache_ttl=0, native_probe_runner=verified_probe)
    tools = gateway.envelope(tools_only=True, refresh=True)
    assert {item["status"] for item in tools["data"]} == {"available"}
    shell = next(item for item in tools["data"] if item["id"] == "tool:code_inspection")
    assert shell["runtime_probe"]["observed_event_types"] == ["command_execution"]
    binding = gateway.validate_requested_tools([{"type": "code_inspection"}])[0]
    assert {"shell", "command_execution"} <= set(binding["_aliases"])
