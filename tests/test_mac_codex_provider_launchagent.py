import copy
import importlib.util
import json
import os
import plistlib
import re
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PLIST_TEMPLATE = ROOT / "ops" / "launchd" / "ru.kolibriai.mac-codex-provider.plist.in"
RUNNER_ACCESS = ROOT / "ops" / "launchd" / "mac-codex-provider.runner-access.json"
LAUNCHER = ROOT / "ops" / "macos" / "mac_codex_provider_launcher.py"
INSTALLER = ROOT / "scripts" / "macos" / "install-mac-codex-provider.py"
HEALTH = ROOT / "scripts" / "macos" / "health-mac-codex-provider.py"
UNINSTALLER = ROOT / "scripts" / "macos" / "uninstall-mac-codex-provider.py"


def load_module(relative_path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def launch_agent_replacements(tmp_path: Path) -> dict[str, str]:
    owner_home = tmp_path / "owner & operator"
    runtime = tmp_path / "runtime-current"
    return {
        "PYTHON_BIN": sys.executable,
        "RUNTIME_DIR": str(runtime),
        "SANITIZED_LOG": str(tmp_path / "logs" / "agent-host.log"),
        "NODE_ID": "mac-owner-client",
        "AGENT_ID": "mac-codex-provider",
        "WORK_ROOT": str(tmp_path / "work"),
        "ARTIFACT_ROOT": str(tmp_path / "artifacts"),
        "USER_HOME": str(owner_home),
        "EXEC_PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        "MESH_MANIFEST": str(tmp_path / "mesh" / "peers.json"),
        "RUNNER_ACCESS": str(tmp_path / "config" / "runner-access.json"),
        "PROVIDER_CREDENTIAL": str(tmp_path / "config" / "external-provider-actor.credential"),
        "NODE_LABELS_JSON": json.dumps(
            {"runtime": "macos", "role": "owner-codex-provider"},
            separators=(",", ":"),
        ),
        "BOOTSTRAP_LOG": str(tmp_path / "logs" / "launchd-bootstrap.log"),
    }


def write_test_provider_credential(path: Path, node_id: str = "mac-codex-provider") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": "kolibri.external-provider-credential.v1",
        "credential_id": "test-provider-v1",
        "node_id": node_id,
        "epoch": 1,
        "token": "test-only-" + "x" * 40,
    }), encoding="utf-8")
    path.chmod(0o600)


def rendered_payload(tmp_path: Path):
    common = load_module(
        "scripts/macos/mac_codex_provider_common.py",
        f"mac_provider_common_{tmp_path.name}",
    )
    rendered, payload = common.render_launch_agent(
        PLIST_TEMPLATE,
        launch_agent_replacements(tmp_path),
    )
    return common, rendered, payload


def test_launchagent_is_dynamic_home_keepalive_and_current_user_contract(tmp_path):
    common, rendered, payload = rendered_payload(tmp_path)

    assert plistlib.loads(rendered) == payload
    assert payload["Label"] == common.LABEL
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] == {"SuccessfulExit": False}
    assert payload["ThrottleInterval"] >= 10
    assert payload["ExitTimeOut"] >= 10
    assert payload["Umask"] == 0o77
    assert payload["StandardOutPath"] == "/dev/null"

    arguments = payload["ProgramArguments"]
    environment = payload["EnvironmentVariables"]
    assert "--control-url" not in arguments
    assert "--control-urls" not in arguments
    assert environment["HOME"].endswith("owner & operator")
    assert environment["KOLIBRI_MESH_MEMBERSHIP_MANIFEST"].endswith("peers.json")
    assert environment["KOLIBRI_RUNNER_ACCESS_MANIFEST"].endswith("runner-access.json")
    assert environment["KOLIBRI_CODEX_READINESS_REFRESH_SECONDS"] == "240"
    assert not common.FORBIDDEN_ENVIRONMENT_KEYS.intersection(environment)

    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True).lower()
    assert "auth.json" not in serialized
    assert "/.codex/" not in serialized
    assert not re.search(r"https?://(?:\d{1,3}\.){3}\d{1,3}", serialized)
    for legacy_identity in ('"main"', '"primary"'):
        assert legacy_identity not in serialized


def test_launchagent_validator_rejects_static_authority_secrets_and_unsafe_lifecycle(tmp_path):
    common, _rendered, payload = rendered_payload(tmp_path)

    mutations = [
        lambda item: item["EnvironmentVariables"].update(
            {"KOLIBRI_FACTORY_CONTROL_URL": "http://192.0.2.10:9101"}
        ),
        lambda item: item["EnvironmentVariables"].update(
            {"OPENAI_API_KEY": "test-only-placeholder"}
        ),
        lambda item: item["ProgramArguments"].extend(
            ["--control-url", "http://192.0.2.10:9101"]
        ),
        lambda item: item.update({"KeepAlive": False}),
        lambda item: item.update({"RunAtLoad": False}),
        lambda item: item["EnvironmentVariables"].pop(
            "KOLIBRI_MESH_MEMBERSHIP_MANIFEST"
        ),
        lambda item: item["EnvironmentVariables"].update(
            {"KOLIBRI_CODEX_READINESS_REFRESH_SECONDS": "0"}
        ),
    ]
    for mutate in mutations:
        candidate = copy.deepcopy(payload)
        mutate(candidate)
        with pytest.raises(common.MacProviderConfigError):
            common.validate_launch_agent_payload(candidate)


def test_mac_runner_access_uses_browser_device_session_without_auth_copy():
    runner_access = load_module("ops/runner_access.py", "mac_provider_runner_access")
    payload = json.loads(RUNNER_ACCESS.read_text(encoding="utf-8"))

    normalized = runner_access.validate_runner_access_manifest(payload)

    assert normalized["authority"] == "home"
    assert normalized["node_selector"] == "dynamic-membership"
    assert normalized["runners"]["codex"] == {
        "mode": "local_service_account",
        "authorization_flow": "browser_device",
        "identity_ref": "service-user://mac-launchagent-owner",
        "probe": {
            "model": "gpt-5.5",
            "sandbox": "read-only",
            "timeout_seconds": 45,
        },
    }
    assert normalized["runners"]["mimo"] == {"mode": "disabled"}
    serialized = RUNNER_ACCESS.read_text(encoding="utf-8").lower()
    for forbidden in (
        "auth.json",
        "/.codex/",
        "api_key",
        "access_token",
        "refresh_token",
        "private_key",
        "http://",
        "https://",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "line",
    [
        "Authorization: Bearer test-provider-credential",
        "OPENAI_API_KEY=test-provider-credential",
        "refresh_token=test-provider-credential",
        "response contained sk-testprovidercredential",
    ],
)
def test_launcher_redacts_sensitive_child_output(line):
    launcher = load_module(
        "ops/macos/mac_codex_provider_launcher.py",
        f"mac_provider_launcher_redaction_{abs(hash(line))}",
    )

    redacted = launcher.redact_log_line(line)

    assert "test-provider-credential" not in redacted
    assert "testprovidercredential" not in redacted
    assert "redacted sensitive provider log line" in redacted


def test_launcher_secure_log_rotates_with_private_permissions(tmp_path):
    launcher = load_module(
        "ops/macos/mac_codex_provider_launcher.py",
        "mac_provider_launcher_rotation",
    )
    path = tmp_path / "private-logs" / "agent-host.log"
    log = launcher.RotatingSecureLog(path, max_bytes=16)
    try:
        log.write("ordinary status line long enough to rotate")
        log.write("Authorization: Bearer test-provider-credential")
    finally:
        log.close()

    rotated = path.with_suffix(".log.1")
    assert rotated.is_file()
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(rotated.stat().st_mode) == 0o600
    combined = path.read_text(encoding="utf-8") + rotated.read_text(encoding="utf-8")
    assert "test-provider-credential" not in combined
    assert "redacted sensitive provider log line" in combined


def test_launcher_end_to_end_preserves_exit_code_and_never_logs_child_secret(tmp_path):
    log_path = tmp_path / "logs" / "provider.log"
    fake_secret = "test-provider-credential"
    completed = subprocess.run(
        [
            sys.executable,
            str(LAUNCHER),
            "--log-path",
            str(log_path),
            "--",
            sys.executable,
            "-c",
            (
                "import sys; "
                f"print('Authorization: Bearer {fake_secret}'); "
                "raise SystemExit(7)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert completed.returncode == 7
    assert completed.stdout == ""
    assert completed.stderr == ""
    contents = log_path.read_text(encoding="utf-8")
    assert fake_secret not in contents
    assert "redacted sensitive provider log line" in contents
    assert "launcher_started" in contents
    assert "launcher_stopped exit_code=7" in contents
    assert stat.S_IMODE(log_path.stat().st_mode) == 0o600


def test_installer_resolves_only_dynamic_home_from_replicated_manifest(tmp_path, monkeypatch):
    installer = load_module(
        "scripts/macos/install-mac-codex-provider.py",
        "mac_provider_installer_dynamic_home",
    )
    manifest = tmp_path / "replicated-peers.json"
    manifest.write_text(
        json.dumps(
            {
                "peers": {
                    "opaque-home-record": {
                        "node_id": "home",
                        "mesh_ip": "10.77.44.31",
                    },
                    "ordinary-worker-record": {
                        "node_id": "worker-randomized",
                        "mesh_ip": "10.77.44.83",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URL", raising=False)
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URLS", raising=False)

    resolved = installer.resolve_dynamic_home(ROOT, manifest)

    assert resolved == "http://10.77.44.31:9101"


def test_current_user_codex_check_uses_session_status_without_auth_material(tmp_path, monkeypatch):
    installer = load_module(
        "scripts/macos/install-mac-codex-provider.py",
        "mac_provider_installer_current_session",
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Logged in using ChatGPT\n",
            stderr="",
        )

    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    codex_bin = tmp_path / "bin" / "codex"

    assert installer.current_user_codex_ready(
        codex_bin,
        tmp_path / "owner-home",
        "/usr/local/bin:/usr/bin:/bin",
    ) is True
    command, kwargs = calls[0]
    assert command == [str(codex_bin), "login", "status"]
    assert kwargs["capture_output"] is True
    assert kwargs["env"] == {
        "HOME": str(tmp_path / "owner-home"),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
    }
    serialized = json.dumps(kwargs["env"], sort_keys=True).lower()
    assert "codex_home" not in serialized
    assert "auth.json" not in serialized
    assert "token" not in serialized
    assert "api_key" not in serialized


def test_immutable_runtime_install_is_private_idempotent_and_tamper_evident(tmp_path):
    installer = load_module(
        "scripts/macos/install-mac-codex-provider.py",
        "mac_provider_installer_runtime",
    )
    layout = installer.MacProviderLayout.from_home(tmp_path / "owner")
    source_a = tmp_path / "source-a.py"
    source_b = tmp_path / "source-b.py"
    source_a.write_text("print('a')\n", encoding="utf-8")
    source_b.write_text("print('b')\n", encoding="utf-8")
    files = [(source_a, "source-a.py"), (source_b, "source-b.py")]
    digest = installer.runtime_digest(files)

    release = installer.install_runtime(layout, files, digest)

    assert release == layout.releases / digest
    assert stat.S_IMODE(layout.releases.stat().st_mode) == 0o700
    assert stat.S_IMODE((release / "source-a.py").stat().st_mode) == 0o500
    assert stat.S_IMODE((release / installer.MANAGED_MARKER).stat().st_mode) == 0o400
    assert installer.install_runtime(layout, files, digest) == release

    (release / "source-a.py").chmod(0o700)
    (release / "source-a.py").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(
        installer.MacProviderConfigError,
        match="runtime_release_digest_mismatch",
    ):
        installer.install_runtime(layout, files, digest)


def test_existing_launchagent_must_be_regular_and_owned_by_label(tmp_path):
    installer = load_module(
        "scripts/macos/install-mac-codex-provider.py",
        "mac_provider_installer_existing_plist",
    )
    path = tmp_path / "provider.plist"
    path.write_bytes(plistlib.dumps({"Label": "com.example.foreign"}))

    with pytest.raises(
        installer.MacProviderConfigError,
        match="existing_launch_agent_not_managed",
    ):
        installer.safe_existing_plist(path)

    path.unlink()
    target = tmp_path / "managed.plist"
    target.write_bytes(plistlib.dumps({"Label": installer.LABEL}))
    path.symlink_to(target)
    with pytest.raises(
        installer.MacProviderConfigError,
        match="existing_launch_agent_unsafe",
    ):
        installer.safe_existing_plist(path)


def test_installer_dry_run_is_read_only_and_never_calls_launchctl(tmp_path, monkeypatch, capsys):
    installer = load_module(
        "scripts/macos/install-mac-codex-provider.py",
        "mac_provider_installer_dry_run",
    )
    owner_home = tmp_path / "owner"
    owner_home.mkdir()
    manifest = tmp_path / "peers.json"
    manifest.write_text(
        json.dumps({"peers": [{"node_id": "home", "mesh_ip": "10.66.55.44"}]}),
        encoding="utf-8",
    )
    codex_bin = tmp_path / "codex"
    codex_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    codex_bin.chmod(0o700)
    monkeypatch.setenv("HOME", str(owner_home))
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URL", raising=False)
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URLS", raising=False)
    monkeypatch.setattr(installer.os, "geteuid", lambda: 501)
    monkeypatch.setattr(installer, "current_user_codex_ready", lambda *_args: True)
    monkeypatch.setattr(
        installer,
        "launchctl",
        lambda *_args, **_kwargs: pytest.fail("dry-run called launchctl"),
    )

    exit_code = installer.main(
        [
            "--mesh-manifest",
            str(manifest),
            "--source-root",
            str(ROOT),
            "--python-bin",
            sys.executable,
            "--codex-bin",
            str(codex_bin),
            "--node-id",
            "mac-dynamic-owner",
        ]
    )

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "validated"
    assert result["apply"] is False
    assert result["load"] is False
    assert result["control_plane_source"] == "replicated_mesh_manifest"
    assert result["control_plane_url"] == "http://10.66.55.44:9101"
    assert result["codex_readiness_refresh_seconds"] == 240
    assert not (owner_home / "Library" / "Application Support" / "Kolibri").exists()


def test_install_load_failure_restores_previous_managed_launchagent(tmp_path, monkeypatch):
    installer = load_module(
        "scripts/macos/install-mac-codex-provider.py",
        "mac_provider_installer_rollback",
    )
    owner_home = tmp_path / "owner"
    owner_home.mkdir()
    layout = installer.MacProviderLayout.from_home(owner_home)
    write_test_provider_credential(layout.provider_credential)
    layout.launch_agent.parent.mkdir(parents=True)
    previous_plist = plistlib.dumps(
        {
            "Label": installer.LABEL,
            "KolibriManagedContract": "kolibri.mac-codex-provider.launchagent.v1",
            "PreviousReleaseEvidence": "must-be-restored-byte-for-byte",
        }
    )
    layout.launch_agent.write_bytes(previous_plist)
    manifest = tmp_path / "peers.json"
    manifest.write_text(
        json.dumps({"peers": [{"node_id": "home", "mesh_ip": "10.57.38.21"}]}),
        encoding="utf-8",
    )
    codex_bin = tmp_path / "codex"
    codex_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    codex_bin.chmod(0o700)
    calls = []
    bootstrap_attempts = 0

    def fake_launchctl(command, **kwargs):
        nonlocal bootstrap_attempts
        calls.append((command, kwargs))
        if command[:1] == ["bootstrap"]:
            bootstrap_attempts += 1
        if command[:1] == ["bootstrap"] and bootstrap_attempts <= 4:
            raise installer.MacProviderConfigError("launchctl_operation_failed")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URL", raising=False)
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URLS", raising=False)
    monkeypatch.setattr(installer.os, "geteuid", lambda: 501)
    monkeypatch.setattr(
        installer.MacProviderLayout,
        "from_home",
        classmethod(lambda _cls, _home: layout),
    )
    monkeypatch.setattr(installer, "current_user_codex_ready", lambda *_args: True)
    monkeypatch.setattr(installer, "launchctl", fake_launchctl)
    monkeypatch.setattr(installer.time, "sleep", lambda _seconds: None)

    with pytest.raises(
        installer.MacProviderConfigError,
        match="launchctl_operation_failed",
    ):
        installer.main(
            [
                "--mesh-manifest",
                str(manifest),
                "--source-root",
                str(ROOT),
                "--python-bin",
                sys.executable,
                "--codex-bin",
                str(codex_bin),
                "--apply",
                "--load",
            ]
        )

    assert layout.launch_agent.read_bytes() == previous_plist
    assert stat.S_IMODE(layout.launch_agent.stat().st_mode) == 0o600
    assert layout.runner_access.read_bytes() == RUNNER_ACCESS.read_bytes()
    bootstrap_calls = [call for call in calls if call[0][:1] == ["bootstrap"]]
    assert len(bootstrap_calls) == 5
    assert bootstrap_calls[-1] == (
        ["bootstrap", "gui/501", str(layout.launch_agent)],
        {},
    )
    assert all(
        call[0] == ["bootout", f"gui/501/{installer.LABEL}"]
        and call[1] == {"tolerate_missing": True}
        for call in calls
        if call[0][:1] == ["bootout"]
    )


def test_mac_provider_sources_never_reference_or_copy_codex_auth_file():
    package_paths = [
        PLIST_TEMPLATE,
        RUNNER_ACCESS,
        LAUNCHER,
        ROOT / "scripts" / "macos" / "mac_codex_provider_common.py",
        INSTALLER,
        HEALTH,
        UNINSTALLER,
    ]
    serialized = "\n".join(path.read_text(encoding="utf-8") for path in package_paths).lower()

    assert "auth.json" not in serialized
    assert "/.codex/" not in serialized
    assert "openai_api_key" not in serialized.replace('"openai_api_key",', "")
    assert "copytree" not in serialized


def test_mac_provider_package_contains_no_fixed_fleet_ip_or_legacy_authority():
    package_paths = [
        PLIST_TEMPLATE,
        RUNNER_ACCESS,
        LAUNCHER,
        ROOT / "scripts" / "macos" / "mac_codex_provider_common.py",
        INSTALLER,
        HEALTH,
        UNINSTALLER,
    ]
    serialized = "\n".join(path.read_text(encoding="utf-8") for path in package_paths)

    assert not re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", serialized)
    lowered = serialized.lower()
    for legacy_identity in ('"main"', "'main'", '"primary"', "'primary'"):
        assert legacy_identity not in lowered


def test_health_accepts_the_actual_agenthost_codex_readiness_shape(tmp_path, monkeypatch, capsys):
    health = load_module(
        "scripts/macos/health-mac-codex-provider.py",
        "mac_provider_health_agenthost_contract",
    )
    owner_home = tmp_path / "owner"
    owner_home.mkdir()
    layout = health.MacProviderLayout.from_home(owner_home)
    write_test_provider_credential(layout.provider_credential)
    layout.logs.mkdir(parents=True)
    for log_path in (layout.sanitized_log, layout.bootstrap_log):
        log_path.write_text("safe\n", encoding="utf-8")
        log_path.chmod(0o600)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    runner_access = tmp_path / "runner-access.json"
    runner_access.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(owner_home))
    monkeypatch.setattr(
        health.MacProviderLayout,
        "from_home",
        classmethod(lambda _cls, _home: layout),
    )
    monkeypatch.setattr(
        health,
        "load_installed_contract",
        lambda _layout: ({}, runtime_dir, runner_access, "http://10.48.17.29:9101"),
    )
    monkeypatch.setattr(health, "launch_agent_loaded", lambda: True)
    monkeypatch.setattr(
        health,
        "fetch_node",
        lambda *_args: {
            "node_id": "mac-codex-provider",
            "capabilities": ["generic_implementation", "runner:codex"],
            "runners": {
                "codex": {
                    "status": "available",
                    "login_status": "authenticated",
                    "readiness_contract": "kolibri.codex-readiness.v1",
                    "probe": {
                        "model": "gpt-5.5",
                        "sandbox": "read-only",
                        "status": "passed",
                    },
                },
                "mimo": {"status": "disabled", "error_type": "runner_disabled"},
            },
            "runner_readiness": {
                "codex": {
                    "schema_version": "kolibri.codex-readiness.v1",
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "status": "available",
                    "login_status": "authenticated",
                    "probe": {
                        "model": "gpt-5.5",
                        "sandbox": "read-only",
                        "status": "passed",
                    },
                }
            },
        },
    )

    result = health.main([])

    evidence = json.loads(capsys.readouterr().out)
    assert result == 0
    assert evidence["status"] == "passed"
    assert evidence["passed"] is True
    assert all(evidence["checks"].values())
    assert evidence["codex_readiness_refresh_seconds"] == 240


def test_health_readiness_freshness_is_bounded():
    health = load_module(
        "scripts/macos/health-mac-codex-provider.py",
        "mac_provider_health_readiness_freshness",
    )
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)

    assert health.readiness_is_fresh(
        (now - timedelta(seconds=300)).isoformat(), now=now,
    ) is True
    assert health.readiness_is_fresh(
        (now - timedelta(seconds=301)).isoformat(), now=now,
    ) is False
    assert health.readiness_is_fresh(
        (now + timedelta(seconds=61)).isoformat(), now=now,
    ) is False
    assert health.readiness_is_fresh("2026-07-11T12:00:00", now=now) is False


def test_health_validate_only_never_contacts_launchctl_or_control_plane(
    tmp_path,
    monkeypatch,
    capsys,
):
    health = load_module(
        "scripts/macos/health-mac-codex-provider.py",
        "mac_provider_health_validate_only",
    )
    owner_home = tmp_path / "owner"
    owner_home.mkdir()
    layout = health.MacProviderLayout.from_home(owner_home)
    write_test_provider_credential(layout.provider_credential)
    layout.logs.mkdir(parents=True)
    layout.sanitized_log.write_text("sanitized\n", encoding="utf-8")
    layout.bootstrap_log.write_text("bootstrap\n", encoding="utf-8")
    layout.sanitized_log.chmod(0o600)
    layout.bootstrap_log.chmod(0o600)
    runner_access = tmp_path / "runner-access.json"
    runner_access.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(owner_home))
    monkeypatch.setattr(
        health.MacProviderLayout,
        "from_home",
        classmethod(lambda _cls, _home: layout),
    )
    monkeypatch.setattr(
        health,
        "load_installed_contract",
        lambda _layout: ({}, tmp_path / "runtime", runner_access, "http://10.48.17.29:9101"),
    )
    monkeypatch.setattr(
        health,
        "launch_agent_loaded",
        lambda: pytest.fail("validate-only called launchctl"),
    )
    monkeypatch.setattr(
        health,
        "fetch_node",
        lambda *_args: pytest.fail("validate-only contacted the Control Plane"),
    )

    result = health.main(["--validate-only"])

    evidence = json.loads(capsys.readouterr().out)
    assert result == 0
    assert evidence["passed"] is True
    assert evidence["validate_only"] is True
    assert evidence["control_plane_source"] == "replicated_mesh_manifest"


def test_health_fetch_is_bounded_direct_and_sends_no_credentials(monkeypatch):
    health = load_module(
        "scripts/macos/health-mac-codex-provider.py",
        "mac_provider_health_fetch",
    )
    observed = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, size):
            observed["read_size"] = size
            return json.dumps({"node_id": "mac-owner"}).encode("utf-8")

    class Opener:
        def open(self, request, timeout):
            observed["url"] = request.full_url
            observed["headers"] = dict(request.header_items())
            observed["timeout"] = timeout
            return Response()

    def fake_build_opener(*handlers):
        observed["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(health.urllib.request, "build_opener", fake_build_opener)

    card = health.fetch_node("http://10.48.17.29:9101", "mac-owner", 7)

    assert card == {"node_id": "mac-owner"}
    assert observed["url"] == "http://10.48.17.29:9101/v1/nodes/mac-owner?scope=all"
    assert observed["timeout"] == 7
    assert observed["read_size"] == health.MAX_HEALTH_BYTES + 1
    assert observed["headers"] == {"Accept": "application/json"}
    assert len(observed["handlers"]) == 1
    assert observed["handlers"][0].proxies == {}


def test_uninstaller_dry_run_is_non_mutating_and_preserves_user_state(
    tmp_path,
    monkeypatch,
    capsys,
):
    uninstaller = load_module(
        "scripts/macos/uninstall-mac-codex-provider.py",
        "mac_provider_uninstaller_dry_run",
    )
    owner_home = tmp_path / "owner"
    owner_home.mkdir()
    layout = uninstaller.MacProviderLayout.from_home(owner_home)
    layout.launch_agent.parent.mkdir(parents=True)
    layout.launch_agent.write_bytes(
        plistlib.dumps(
            {
                "Label": uninstaller.LABEL,
                "KolibriManagedContract": "kolibri.mac-codex-provider.launchagent.v1",
            }
        )
    )
    state_paths = [
        layout.runner_access,
        layout.work / "task-state",
        layout.artifacts / "artifact-state",
        layout.logs / "provider.log",
    ]
    for path in state_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("preserve\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(owner_home))
    monkeypatch.setattr(
        uninstaller.MacProviderLayout,
        "from_home",
        classmethod(lambda _cls, _home: layout),
    )
    monkeypatch.setattr(uninstaller.os, "geteuid", lambda: 501)
    monkeypatch.setattr(
        uninstaller,
        "launchctl",
        lambda *_args, **_kwargs: pytest.fail("dry-run called launchctl"),
    )

    result = uninstaller.main([])

    evidence = json.loads(capsys.readouterr().out)
    assert result == 0
    assert evidence["status"] == "validated"
    assert evidence["apply"] is False
    assert layout.launch_agent.is_file()
    assert all(path.read_text(encoding="utf-8") == "preserve\n" for path in state_paths)
    assert set(evidence["preserved"]) >= {
        "codex_session",
        "mesh_manifest",
        "runner_access",
        "worktrees",
        "artifacts",
        "logs",
    }


def test_uninstaller_apply_removes_only_launchagent_by_default(tmp_path, monkeypatch, capsys):
    uninstaller = load_module(
        "scripts/macos/uninstall-mac-codex-provider.py",
        "mac_provider_uninstaller_apply",
    )
    owner_home = tmp_path / "owner"
    owner_home.mkdir()
    layout = uninstaller.MacProviderLayout.from_home(owner_home)
    layout.launch_agent.parent.mkdir(parents=True)
    layout.launch_agent.write_bytes(
        plistlib.dumps(
            {
                "Label": uninstaller.LABEL,
                "KolibriManagedContract": "kolibri.mac-codex-provider.launchagent.v1",
            }
        )
    )
    state_paths = [
        layout.runner_access,
        layout.work / "task-state",
        layout.artifacts / "artifact-state",
        layout.logs / "provider.log",
    ]
    for path in state_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("preserve\n", encoding="utf-8")
    calls = []
    monkeypatch.setenv("HOME", str(owner_home))
    monkeypatch.setattr(
        uninstaller.MacProviderLayout,
        "from_home",
        classmethod(lambda _cls, _home: layout),
    )
    monkeypatch.setattr(uninstaller.os, "geteuid", lambda: 501)
    monkeypatch.setattr(
        uninstaller,
        "launchctl",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )

    result = uninstaller.main(["--apply"])

    evidence = json.loads(capsys.readouterr().out)
    assert result == 0
    assert evidence["status"] == "uninstalled"
    assert not layout.launch_agent.exists()
    assert all(path.read_text(encoding="utf-8") == "preserve\n" for path in state_paths)
    assert calls == [
        (["bootout", f"gui/501/{uninstaller.LABEL}"], {"tolerate_missing": True})
    ]


def test_runtime_removal_preserves_unmanaged_content_when_releases_are_missing(tmp_path):
    uninstaller = load_module(
        "scripts/macos/uninstall-mac-codex-provider.py",
        "mac_provider_uninstaller_unmanaged_runtime",
    )
    layout = uninstaller.MacProviderLayout.from_home(tmp_path / "owner")
    runtime_root = layout.releases.parent
    runtime_root.mkdir(parents=True)
    unrelated = runtime_root / "unmanaged-user-data.txt"
    unrelated.write_text("must survive\n", encoding="utf-8")

    assert uninstaller.remove_managed_runtime(layout) is False

    assert unrelated.read_text(encoding="utf-8") == "must survive\n"


def test_runtime_removal_accepts_only_marker_owned_releases_and_preserves_other_state(tmp_path):
    uninstaller = load_module(
        "scripts/macos/uninstall-mac-codex-provider.py",
        "mac_provider_uninstaller_managed_runtime",
    )
    layout = uninstaller.MacProviderLayout.from_home(tmp_path / "owner")
    release = layout.releases / ("a" * 64)
    release.mkdir(parents=True)
    (release / uninstaller.MANAGED_MARKER).write_text(
        f"{uninstaller.LABEL}\n",
        encoding="utf-8",
    )
    (release / "agent_host.py").write_text("# managed runtime\n", encoding="utf-8")
    layout.runner_access.parent.mkdir(parents=True, exist_ok=True)
    layout.runner_access.write_text("preserve config\n", encoding="utf-8")

    assert uninstaller.remove_managed_runtime(layout) is True
    assert not layout.releases.parent.exists()
    assert layout.runner_access.read_text(encoding="utf-8") == "preserve config\n"


def test_runtime_removal_fails_closed_on_unmanaged_release_and_preserves_everything(tmp_path):
    uninstaller = load_module(
        "scripts/macos/uninstall-mac-codex-provider.py",
        "mac_provider_uninstaller_reject_unmanaged_release",
    )
    layout = uninstaller.MacProviderLayout.from_home(tmp_path / "owner")
    managed = layout.releases / ("a" * 64)
    managed.mkdir(parents=True)
    (managed / uninstaller.MANAGED_MARKER).write_text(
        f"{uninstaller.LABEL}\n",
        encoding="utf-8",
    )
    unmanaged = layout.releases / "unmanaged-release"
    unmanaged.mkdir()
    evidence = unmanaged / "must-survive.txt"
    evidence.write_text("preserve\n", encoding="utf-8")

    with pytest.raises(
        uninstaller.MacProviderConfigError,
        match="runtime_release_not_managed",
    ):
        uninstaller.remove_managed_runtime(layout)

    assert managed.is_dir()
    assert evidence.read_text(encoding="utf-8") == "preserve\n"
