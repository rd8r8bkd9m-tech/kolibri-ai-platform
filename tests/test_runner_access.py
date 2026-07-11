import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(relative_path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def default_payload():
    return json.loads((ROOT / "ops" / "runner-access.default.json").read_text(encoding="utf-8"))


def agent_args(tmp_path: Path):
    manifest = tmp_path / "mesh.json"
    manifest.write_text(
        json.dumps({"peers": [{"node_id": "home", "mesh_ip": "10.99.0.1"}]}),
        encoding="utf-8",
    )
    return argparse.Namespace(
        control_url="http://10.99.0.1:9101",
        mesh_membership_manifest=str(manifest),
        node_id="worker-readiness-test",
        agent_id="agent-host-readiness-test",
        capabilities="generic_implementation,runner:codex,runner_codex,codex_runner",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )


def test_default_manifest_is_dynamic_home_browser_device_contract():
    runner_access = load_module("ops/runner_access.py", "runner_access_default_test")

    normalized = runner_access.validate_runner_access_manifest(default_payload())

    assert normalized["authority"] == "home"
    assert normalized["node_selector"] == "dynamic-membership"
    assert normalized["runners"]["codex"] == {
        "mode": "local_service_account",
        "authorization_flow": "browser_device",
        "identity_ref": "service-user://kolibri-agent",
        "probe": {"model": "gpt-5.5", "sandbox": "read-only", "timeout_seconds": 45},
    }


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda value: value.update({"api_key": "sk-test"}), "runner_access_raw_secret_field_forbidden"),
        (
            lambda value: value["runners"]["codex"].update({"identity_ref": "file:///home/user/.codex/auth.json"}),
            "runner_access_raw_auth_or_endpoint_forbidden",
        ),
        (
            lambda value: value.update({"node_selector": "fixed-list"}),
            "runner_access_node_selector_must_be_dynamic",
        ),
        (
            lambda value: value.update({"control_plane_endpoint": "10.99.0.2:9101"}),
            "runner_access_manifest_unknown_field",
        ),
    ],
)
def test_manifest_rejects_secret_material_and_static_membership(mutation, expected):
    runner_access = load_module("ops/runner_access.py", f"runner_access_reject_{expected}")
    payload = default_payload()
    mutation(payload)

    with pytest.raises(runner_access.RunnerAccessError) as exc_info:
        runner_access.validate_runner_access_manifest(payload)

    assert exc_info.value.code == expected


def test_trusted_broker_declaration_is_non_secret_and_requires_live_attestation():
    runner_access = load_module("ops/runner_access.py", "runner_access_broker_test")
    payload = default_payload()
    payload["runners"]["codex"] = {
        "mode": "trusted_broker",
        "broker_ref": "runner-broker://home/codex",
        "authorization_ref": "control-plane://home/codex-runner",
    }

    normalized = runner_access.validate_runner_access_manifest(payload)

    assert normalized["runners"]["codex"]["requires_runtime_attestation"] is True


def test_codex_capability_requires_login_and_real_gpt55_readonly_probe(tmp_path, monkeypatch):
    agent_host = load_module("ops/agent_host.py", "agent_host_readiness_success")
    runner_manifest = tmp_path / "runner-access.json"
    runner_manifest.write_text(json.dumps(default_payload()), encoding="utf-8")
    monkeypatch.setenv("KOLIBRI_RUNNER_ACCESS_MANIFEST", str(runner_manifest))
    monkeypatch.setattr(
        agent_host.shutil,
        "which",
        lambda name: "/usr/local/bin/codex" if name == "codex" else None,
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append((list(command), dict(kwargs)))
        if command[1:] == ["login", "status"]:
            return SimpleNamespace(returncode=0, stdout="Logged in using ChatGPT\n", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "type": "item.completed",
                "item": {"type": "agent_message", "text": agent_host.CODEX_READINESS_MARKER},
            }) + "\n",
            stderr="",
        )

    monkeypatch.setattr(agent_host.subprocess, "run", fake_run)
    host = agent_host.AgentHost(agent_args(tmp_path))

    status = host.runner_status["codex"]
    assert status["status"] == "available"
    assert status["login_status"] == "authenticated"
    assert status["probe"]["status"] == "passed"
    assert "runner:codex" in host.capabilities
    evidence = host.codex_readiness_evidence()
    assert evidence["schema_version"] == "kolibri.codex-readiness.v1"
    assert evidence["node_id"] == "worker-readiness-test"
    assert evidence["access_mode"] == "local_service_account"
    assert evidence["probe"]["output_sha256"] == status["probe"]["output_sha256"]
    assert "path" not in evidence
    probe_command, probe_kwargs = calls[1]
    assert probe_command[probe_command.index("--model") + 1] == "gpt-5.5"
    assert probe_command[probe_command.index("--sandbox") + 1] == "read-only"
    assert probe_command[-1] == "-"
    assert agent_host.CODEX_READINESS_MARKER not in probe_command
    assert probe_kwargs["input"] == f"Reply with exactly {agent_host.CODEX_READINESS_MARKER} and nothing else."


def test_codex_probe_403_withdraws_capability_and_attributes_codex(tmp_path, monkeypatch):
    agent_host = load_module("ops/agent_host.py", "agent_host_readiness_403")
    runner_manifest = tmp_path / "runner-access.json"
    runner_manifest.write_text(json.dumps(default_payload()), encoding="utf-8")
    monkeypatch.setenv("KOLIBRI_RUNNER_ACCESS_MANIFEST", str(runner_manifest))
    monkeypatch.setattr(
        agent_host.shutil,
        "which",
        lambda name: "/usr/local/bin/codex" if name == "codex" else None,
    )

    def fake_run(command, **_kwargs):
        if command[1:] == ["login", "status"]:
            return SimpleNamespace(returncode=0, stdout="Logged in using ChatGPT\n", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="Cloudflare HTTP 403 forbidden")

    monkeypatch.setattr(agent_host.subprocess, "run", fake_run)
    host = agent_host.AgentHost(agent_args(tmp_path))

    assert host.runner_status["codex"]["status"] == "blocked"
    assert host.runner_status["codex"]["error_type"] == "runner_access_denied"
    assert "runner:codex" not in host.capabilities
    error_type, message, retry = host.classify_runner_error(
        "codex", "probe failed", "Cloudflare HTTP 403 forbidden"
    )
    assert (error_type, retry) == ("runner_access_denied", False)
    assert "codex" in message
    assert "mimo" not in message


def test_periodic_codex_readiness_refresh_is_idle_bounded_and_withdraws_capability(
    tmp_path,
    monkeypatch,
    capsys,
):
    agent_host = load_module("ops/agent_host.py", "agent_host_periodic_readiness")
    runner_manifest = tmp_path / "runner-access.json"
    runner_manifest.write_text(json.dumps(default_payload()), encoding="utf-8")
    monkeypatch.setenv("KOLIBRI_RUNNER_ACCESS_MANIFEST", str(runner_manifest))
    monkeypatch.setattr(
        agent_host.shutil,
        "which",
        lambda name: "/usr/local/bin/codex" if name == "codex" else None,
    )
    calls = []

    def fake_readiness(_self, executable):
        calls.append(executable)
        if len(calls) == 1:
            return {
                "status": "available",
                "path": executable,
                "checked_at": "2026-07-11T01:00:00+00:00",
                "readiness_contract": "kolibri.codex-readiness.v1",
                "login_status": "authenticated",
                "error_type": None,
                "probe": {
                    "model": "gpt-5.5",
                    "sandbox": "read-only",
                    "status": "passed",
                },
            }
        raise RuntimeError("Authorization: Bearer test-provider-credential")

    monkeypatch.setattr(
        agent_host.AgentHost,
        "detect_codex_runner_status",
        fake_readiness,
    )
    args = agent_args(tmp_path)
    args.codex_readiness_refresh_seconds = 240
    host = agent_host.AgentHost(args)
    host._last_codex_readiness_refresh = 100.0

    assert host.codex_readiness_refresh_seconds == 240
    assert "runner:codex" in host.capabilities
    host._active_task_id = "active-fenced-task"
    assert host.refresh_codex_readiness_if_due(now=400.0) is False
    assert len(calls) == 1

    host._active_task_id = None
    assert host.refresh_codex_readiness_if_due(now=400.0) is True
    assert len(calls) == 2
    assert host.runner_status["codex"]["status"] == "unavailable"
    assert host.runner_status["codex"]["error_type"] == "runner_readiness_refresh_failed"
    assert "runner:codex" not in host.capabilities
    assert host.refresh_codex_readiness_if_due(now=500.0) is False
    assert len(calls) == 2
    captured = capsys.readouterr()
    assert "test-provider-credential" not in f"{captured.out}\n{captured.err}"


def test_periodic_codex_readiness_refresh_is_disabled_by_default(tmp_path, monkeypatch):
    agent_host = load_module("ops/agent_host.py", "agent_host_readiness_default_disabled")
    runner_manifest = tmp_path / "runner-access.json"
    runner_manifest.write_text(json.dumps(default_payload()), encoding="utf-8")
    monkeypatch.setenv("KOLIBRI_RUNNER_ACCESS_MANIFEST", str(runner_manifest))
    calls = []
    monkeypatch.setattr(
        agent_host.AgentHost,
        "detect_codex_runner_status",
        lambda _self, executable: calls.append(executable) or {
            "status": "unavailable",
            "checked_at": "2026-07-11T01:00:00+00:00",
            "error_type": "runner_unavailable",
        },
    )

    host = agent_host.AgentHost(agent_args(tmp_path))

    assert host.codex_readiness_refresh_seconds == 0
    assert host.refresh_codex_readiness_if_due(now=100_000.0) is False
    assert len(calls) == 1

    minimum_args = agent_args(tmp_path)
    minimum_args.codex_readiness_refresh_seconds = 1
    assert agent_host.AgentHost(minimum_args).codex_readiness_refresh_seconds == 60
    maximum_args = agent_args(tmp_path)
    maximum_args.codex_readiness_refresh_seconds = 99_999
    assert agent_host.AgentHost(maximum_args).codex_readiness_refresh_seconds == 3_600


def test_codex_binary_without_access_manifest_never_advertises_capability(tmp_path, monkeypatch):
    agent_host = load_module("ops/agent_host.py", "agent_host_readiness_missing_manifest")
    monkeypatch.setenv("KOLIBRI_RUNNER_ACCESS_MANIFEST", str(tmp_path / "missing.json"))
    monkeypatch.setattr(
        agent_host.shutil,
        "which",
        lambda name: "/usr/local/bin/codex" if name == "codex" else None,
    )

    host = agent_host.AgentHost(agent_args(tmp_path))

    assert host.runner_status["codex"]["error_type"] == "runner_access_manifest_missing"
    assert "runner:codex" not in host.capabilities
    assert "runner_codex" not in host.capabilities
    assert "codex_runner" not in host.capabilities


def test_disabled_mimo_policy_overrides_binary_and_declared_capability(tmp_path, monkeypatch):
    agent_host = load_module("ops/agent_host.py", "agent_host_mimo_disabled")
    payload = default_payload()
    payload["runners"]["codex"] = {"mode": "disabled"}
    payload["runners"]["mimo"] = {"mode": "disabled"}
    runner_manifest = tmp_path / "runner-access.json"
    runner_manifest.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("KOLIBRI_RUNNER_ACCESS_MANIFEST", str(runner_manifest))
    monkeypatch.setattr(
        agent_host.shutil,
        "which",
        lambda name: f"/usr/local/bin/{name}" if name in {"codex", "mimo"} else None,
    )
    args = agent_args(tmp_path)
    args.capabilities += ",runner:mimo,runner_mimo,mimo_runner"

    host = agent_host.AgentHost(args)

    assert host.runner_status["mimo"]["status"] == "disabled"
    assert host.runner_status["mimo"]["error_type"] == "runner_disabled"
    assert "runner:mimo" not in host.capabilities
    assert "runner_mimo" not in host.capabilities
    assert "mimo_runner" not in host.capabilities


def test_default_manifest_contains_no_endpoint_or_auth_file_reference():
    text = (ROOT / "ops" / "runner-access.default.json").read_text(encoding="utf-8").lower()
    assert "auth.json" not in text
    assert "/.codex/" not in text
    assert "http://" not in text
    assert "https://" not in text
    assert "10.99." not in text
    assert '"main"' not in text
    assert '"primary"' not in text


def test_readiness_evidence_schema_is_strict_and_secret_free():
    schema = json.loads(
        (ROOT / "contracts" / "codex-runner-readiness.schema.json").read_text(encoding="utf-8")
    )
    assert schema["additionalProperties"] is False
    assert schema["properties"]["probe"]["additionalProperties"] is False
    serialized = json.dumps(schema, sort_keys=True).lower()
    for forbidden in ("api_key", "access_token", "refresh_token", "auth.json", "private_key"):
        assert forbidden not in serialized


def test_systemd_and_dynamic_installers_ship_only_the_non_secret_declaration():
    service = (ROOT / "ops" / "systemd" / "kolibri-agent-host.service").read_text(encoding="utf-8")
    provision = (ROOT / "scripts" / "provision-server.sh").read_text(encoding="utf-8")
    rollout = (ROOT / "scripts" / "rollout-home-only-bootstrap.sh").read_text(encoding="utf-8")

    assert "KOLIBRI_RUNNER_ACCESS_MANIFEST=/etc/kolibri/runner-access.json" in service
    for script in (provision, rollout):
        assert "runner_access.py" in script
        assert "runner-access.default.json" in script
        assert "/etc/kolibri/runner-access.json" in script
        assert "auth.json" not in script
        assert "/.codex/" not in script
    for fixed_worker_name in ("main", "primary", "kfrm", "highload"):
        assert f'"{fixed_worker_name}"' not in rollout
        assert f"{fixed_worker_name}|" not in rollout
        assert f"|{fixed_worker_name}" not in rollout
