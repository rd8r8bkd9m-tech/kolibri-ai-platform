from __future__ import annotations

import importlib.util
import argparse
import json
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "linux" / "install-home-codex-provider.py"


def load_installer(name: str = "home_codex_provider_installer"):
    spec = importlib.util.spec_from_file_location(name, INSTALLER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def mesh_manifest(path: Path) -> Path:
    path.write_text(json.dumps({
        "schema_version": 3,
        "peers": {
            "10.99.0.1": {"node_id": "home", "mesh_ip": "10.99.0.1"},
            "10.99.0.8": {"node_id": "worker-a", "mesh_ip": "10.99.0.8"},
        },
    }), encoding="utf-8")
    return path


def executable(path: Path, source: str) -> Path:
    path.write_text(f"#!/bin/sh\n{source}\n", encoding="utf-8")
    path.chmod(0o700)
    return path


def test_dry_run_builds_home_only_service_without_copying_codex_auth(
    tmp_path, monkeypatch, capsys,
):
    installer = load_installer("home_codex_provider_dry_run")
    home = tmp_path / "home"
    home.mkdir()
    manifest = mesh_manifest(tmp_path / "peers.json")
    codex = executable(tmp_path / "codex", "echo 'Logged in using browser session'")
    python = Path(sys.executable)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(
        installer,
        "assert_local_home",
        lambda _root, _manifest, _interface: "10.99.0.1",
    )
    monkeypatch.setattr(installer, "user_linger_enabled", lambda: True)

    assert installer.main([
        "--mesh-manifest", str(manifest),
        "--source-root", str(ROOT),
        "--python-bin", str(python),
        "--codex-bin", str(codex),
        "--provider-proxy-url", "http://127.0.0.1:18080",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "validated"
    assert payload["node_id"] == "home-codex-provider"
    assert payload["actor_scope"] == "external_provider_actor"
    assert payload["control_plane_authority"] == "home"
    assert payload["control_plane_source"] == "replicated_mesh_manifest"
    assert payload["runtime"] == "home_systemd_user"
    assert payload["public_model"] == "kolibri"
    assert payload["codex_session"] == "current_user_authenticated"
    assert payload["credentials_copied"] is False
    assert payload["credential_present"] is False
    assert payload["persistent_user_manager"] is True
    assert not (home / ".config" / "systemd" / "user").exists()
    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "auth.json" not in serialized
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized
    assert "bearer " not in serialized


def test_rendered_service_uses_api_agent_host_and_scoped_home_identity(tmp_path):
    installer = load_installer("home_codex_provider_render")
    template = ROOT / "ops" / "systemd" / "kolibri-home-codex-provider.service.in"
    base = tmp_path / "home-provider"
    labels = json.dumps({
        "authority": "home",
        "physical_node_id": "home-codex-provider",
        "provider": "codex",
        "runtime": "home_systemd_user",
    }, sort_keys=True, separators=(",", ":"))
    replacements = {
        "MESH_MANIFEST": str(tmp_path / "peers.json"),
        "RUNNER_ACCESS": str(base / "runner-access.json"),
        "PROVIDER_CREDENTIAL": str(base / "credential"),
        "WORK_ROOT": str(base / "work"),
        "ARTIFACT_ROOT": str(base / "artifacts"),
        "USER_HOME": str(tmp_path / "home"),
        "RUNTIME_DIR": str(base / "runtime"),
        "PYTHON_BIN": sys.executable,
        "SANITIZED_LOG": str(base / "agent.log"),
        "HOME_ENV": f"HOME={tmp_path / 'home'}",
        "PATH_ENV": "PATH=/usr/bin:/bin",
        "PYTHONPATH_ENV": f"PYTHONPATH={base / 'runtime'}",
        "PROVIDER_RELEASE_CURRENT_ENV": (
            f"KOLIBRI_RELEASE_CURRENT_LINK={base / 'provider-current'}"
        ),
        "PROVIDER_RELEASE_ROOT_ENV": f"KOLIBRI_RELEASE_ROOT={base / 'releases'}",
        "MESH_MANIFEST_ENV": f"KOLIBRI_MESH_MEMBERSHIP_MANIFEST={tmp_path / 'peers.json'}",
        "RUNNER_ACCESS_ENV": f"KOLIBRI_RUNNER_ACCESS_MANIFEST={base / 'runner-access.json'}",
        "PROVIDER_CREDENTIAL_ENV": (
            f"KOLIBRI_EXTERNAL_PROVIDER_ACTOR_CREDENTIAL_FILE={base / 'credential'}"
        ),
        "NODE_LABELS_ENV": f"KOLIBRI_NODE_LABELS_JSON={labels}",
        "PROVIDER_PROXY_ENV": "KOLIBRI_PROVIDER_PROXY_URL=http://127.0.0.1:18080",
        "NODE_ID": "home-codex-provider",
        "AGENT_ID": "home-codex-provider",
    }
    rendered = installer.render_service(template, replacements).decode()

    assert "agent_host.py" in rendered
    assert "--capabilities codex_provider_broker" in rendered
    assert "--max-inflight 1" in rendered
    assert "--control-url" not in rendered
    assert "KOLIBRI_FACTORY_CONTROL_URL" not in rendered
    assert "KOLIBRI_RELEASE_CURRENT_LINK" in rendered
    assert "provider-current" in rendered
    assert "home_systemd_user" in rendered
    assert "codex-provider" in rendered
    assert rendered.count("ConditionFileNotEmpty=") == 3
    assert "ConditionPathIsRegular=" not in rendered
    assert 'ConditionFileNotEmpty="' not in rendered
    assert (
        "WorkingDirectory=%h/.local/share/kolibri/home-codex-provider/worktrees"
        in rendered
    )
    assert 'WorkingDirectory="' not in rendered
    assert (
        "StandardError=append:%h/.local/share/kolibri/home-codex-provider/logs/systemd-bootstrap.log"
        in rendered
    )
    assert 'StandardError="' not in rendered
    assert "NoNewPrivileges=yes" in rendered
    assert "ProtectSystem=strict" in rendered
    assert "auth.json" not in rendered.lower()
    assert "token=" not in rendered.lower()

    if sys.platform.startswith("linux") and shutil.which("systemd-analyze"):
        unit = tmp_path / "kolibri-home-codex-provider.service"
        unit.write_text(rendered, encoding="utf-8")
        verified = subprocess.run(
            [
                "systemd-analyze",
                "--user",
                "--man=no",
                "--recursive-errors=yes",
                "verify",
                str(unit),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        diagnostic = f"{verified.stdout}\n{verified.stderr}"
        assert verified.returncode == 0, diagnostic
        for forbidden in (
            "Unknown key",
            "Unknown lvalue",
            "not an absolute path",
            "ConditionPathIsRegular",
        ):
            assert forbidden not in diagnostic


@pytest.mark.parametrize("value", [
    "https://127.0.0.1:18080",
    "http://10.99.0.2:18080",
    "http://user@127.0.0.1:18080",
    "http://127.0.0.1:80",
    "http://127.0.0.1:18080/path",
])
def test_provider_proxy_must_be_uncredentialed_local_loopback(value):
    installer = load_installer(f"home_codex_provider_proxy_{abs(hash(value))}")
    with pytest.raises(installer.HomeProviderConfigError) as error:
        installer.validate_proxy_url(value)
    assert error.value.code == "provider_proxy_url_invalid"


def test_local_provider_credential_is_node_bound_and_never_returned(tmp_path):
    installer = load_installer("home_codex_provider_credential")
    credential = tmp_path / "external-provider-actor.credential"
    token = "A" * 48
    credential.write_text(json.dumps({
        "schema_version": "kolibri.external-provider-credential.v1",
        "credential_id": "home-codex-provider-v1",
        "node_id": "home-codex-provider",
        "epoch": 1,
        "token": token,
    }), encoding="utf-8")
    credential.chmod(0o600)

    metadata = installer.validate_local_credential(credential, "home-codex-provider")
    assert metadata == {"credential_id": "home-codex-provider-v1", "epoch": 1}
    assert token not in json.dumps(metadata)

    credential.chmod(0o644)
    with pytest.raises(installer.HomeProviderConfigError) as error:
        installer.validate_local_credential(credential, "home-codex-provider")
    assert error.value.code == "external_provider_actor_credential_unsafe"


def test_runtime_install_is_content_addressed_and_refuses_tampering(tmp_path):
    installer = load_installer("home_codex_provider_runtime")
    home = tmp_path / "home"
    home.mkdir()
    layout = installer.HomeProviderLayout.from_home(home)
    source = tmp_path / "agent_host.py"
    source.write_text("print('safe')\n", encoding="utf-8")
    files = [(source, "agent_host.py")]
    digest = installer.runtime_digest(files)

    installed = installer.install_runtime(layout, files, digest)
    assert installed == layout.releases / digest
    assert stat.S_IMODE((installed / "agent_host.py").stat().st_mode) == 0o500
    assert installer.install_runtime(layout, files, digest) == installed

    (installed / "agent_host.py").chmod(0o700)
    with pytest.raises(installer.HomeProviderConfigError) as error:
        installer.install_runtime(layout, files, digest)
    assert error.value.code == "runtime_release_digest_mismatch"


def test_checked_in_home_runner_policy_is_local_owner_codex_only():
    installer = load_installer("home_codex_provider_policy")
    payload = installer.validate_runner_access(
        ROOT,
        ROOT / "ops" / "systemd" / "home-codex-provider.runner-access.json",
    )
    assert payload["authority"] == "home"
    assert payload["runners"]["codex"]["identity_ref"] == "service-user://home-owner"
    assert payload["runners"]["codex"]["probe"] == {
        "model": "gpt-5.5",
        "sandbox": "read-only",
        "timeout_seconds": 45,
    }
    assert payload["runners"]["mimo"] == {"mode": "disabled"}


def test_service_validator_rejects_static_control_plane_and_secret_material():
    installer = load_installer("home_codex_provider_service_rejections")
    baseline = "\n".join((
        f"# X-Kolibri-Managed-Contract={installer.MANAGED_CONTRACT}",
        "KOLIBRI_MESH_MEMBERSHIP_MANIFEST=/manifest",
        "KOLIBRI_EXTERNAL_PROVIDER_ACTOR_CREDENTIAL_FILE=/credential",
        "KOLIBRI_RELEASE_CURRENT_LINK=/provider-current",
        "KOLIBRI_RELEASE_ROOT=/provider-releases",
        "KOLIBRI_NODE_LABELS_JSON=home_systemd_user",
        "ConditionFileNotEmpty=/manifest",
        "WorkingDirectory=%h/.local/share/kolibri/home-codex-provider/worktrees",
        "StandardError=append:%h/.local/share/kolibri/home-codex-provider/logs/systemd-bootstrap.log",
        "--capabilities codex_provider_broker --max-inflight 1",
        "Restart=on-failure",
        "NoNewPrivileges=yes",
        "ProtectSystem=strict",
    ))
    installer.validate_service(baseline)
    for addition in ("KOLIBRI_FACTORY_CONTROL_URL=http://10.99.0.2", "access_token=secret"):
        with pytest.raises(installer.HomeProviderConfigError) as error:
            installer.validate_service(f"{baseline}\n{addition}")
        assert error.value.code == "service_secret_or_static_authority_forbidden"

    for addition in (
        "ConditionPathIsRegular=/manifest",
        'ConditionFileNotEmpty="/manifest"',
        'WorkingDirectory="/home/ladik/work"',
        'StandardError="append:/home/ladik/bootstrap.log"',
    ):
        with pytest.raises(installer.HomeProviderConfigError) as error:
            installer.validate_service(f"{baseline}\n{addition}")
        assert error.value.code == "service_secret_or_static_authority_forbidden"


@pytest.mark.parametrize("value", [
    "relative/path",
    "/home/ladik/path with spaces",
    "/home/ladik/%h",
    "/home/ladik/path\\escape",
])
def test_systemd_raw_path_rejects_nonportable_values(value):
    installer = load_installer(f"home_codex_provider_systemd_path_{abs(hash(value))}")
    with pytest.raises(installer.HomeProviderConfigError) as error:
        installer.systemd_raw_path(value)
    assert error.value.code == "systemd_path_invalid"


def test_installer_source_never_reads_or_copies_codex_auth_file():
    source = INSTALLER.read_text(encoding="utf-8").lower()
    assert 'path.home() / ".codex"' not in source
    assert "read_auth" not in source
    assert "copytree" not in source
    assert "rsync" not in source
    assert "scp" not in source
    assert "ssh" not in source


def test_agent_host_signs_home_runtime_only_with_home_authority(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "home_provider_agent_host_runtime",
        ROOT / "ops" / "agent_host.py",
    )
    assert spec is not None and spec.loader is not None
    runtime = importlib.util.module_from_spec(spec)
    sys.modules["home_provider_agent_host_runtime"] = runtime
    spec.loader.exec_module(runtime)

    manifest = mesh_manifest(tmp_path / "peers-agent.json")
    runner_access = tmp_path / "runner-access.json"
    runner_access.write_bytes(
        (ROOT / "ops" / "systemd" / "home-codex-provider.runner-access.json").read_bytes()
    )
    credential = tmp_path / "external-provider-actor.credential"
    credential.write_text(json.dumps({
        "schema_version": "kolibri.external-provider-credential.v1",
        "credential_id": "home-codex-provider-v1",
        "node_id": "home-codex-provider",
        "epoch": 1,
        "token": "T" * 48,
    }), encoding="utf-8")
    credential.chmod(0o600)
    monkeypatch.setenv("KOLIBRI_RUNNER_ACCESS_MANIFEST", str(runner_access))
    monkeypatch.setattr(runtime.AgentHost, "detect_runner_status", lambda _self: {})
    args = argparse.Namespace(
        control_url="http://10.99.0.1:9101",
        control_urls=None,
        mesh_membership_manifest=str(manifest),
        node_id="home-codex-provider",
        agent_id="home-codex-provider",
        capabilities="codex_provider_broker",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=5,
        max_inflight=1,
        codex_readiness_refresh_seconds=240,
        external_provider_credential_file=str(credential),
        labels_json=json.dumps({
            "authority": "home",
            "physical_node_id": "home-codex-provider",
            "provider": "codex",
            "runtime": "home_systemd_user",
        }),
    )

    host = runtime.AgentHost(args)
    assert host._external_provider_actor is True
    assert host._external_provider_credential["node_id"] == "home-codex-provider"
    headers = runtime.external_provider_request_headers(
        host._external_provider_credential,
        host.node_id,
        "POST",
        "/v1/nodes/home-codex-provider/heartbeat",
        {"health": "online"},
    )
    assert headers["X-Kolibri-Actor-Contract"] == "kolibri.external-provider-hmac.v1"
    assert headers["X-Kolibri-Actor-Node"] == "home-codex-provider"
    assert headers["X-Kolibri-Actor-Credential"] == "home-codex-provider-v1"
    assert len(headers["X-Kolibri-Actor-Signature"]) == 64

    args.labels_json = json.dumps({
        "physical_node_id": "home-codex-provider",
        "provider": "codex",
        "runtime": "home_systemd_user",
    })
    unsigned = runtime.AgentHost(args)
    assert unsigned._external_provider_actor is False
    assert unsigned._external_provider_credential is None
