from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_ROOTS = (ROOT / "ops", ROOT / "scripts", ROOT / "backend", ROOT / "infra", ROOT / "deploy")
ACTIVE_SUFFIXES = {".py", ".sh", ".service"}
IGNORED_PARTS = {"__pycache__", ".venv", "venv", "node_modules", "tests"}


def active_runtime_files() -> list[Path]:
    files: list[Path] = []
    for root in ACTIVE_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or IGNORED_PARTS.intersection(path.parts):
                continue
            if path.suffix in ACTIVE_SUFFIXES or path.name == "kolibri-dispatch":
                files.append(path)
    return sorted(files)


def test_active_runtime_has_no_legacy_control_plane_endpoint_or_static_authority_list():
    offenders: list[str] = []
    static_authority_list = re.compile(
        r"KOLIBRI_FACTORY_CONTROL_URLS?\s*=\s*['\"][^'\"\n]*,[^'\"\n]*['\"]"
    )
    legacy_runtime_literal = re.compile(
        r"(?:10\.99\.0\.2:9101|primary-candidate|kolibri-(?:main|primary)|"
        r"(?<!\d)78\.\d{1,3}\.\d{1,3}\.\d{1,3}(?!\d))"
    )
    for path in active_runtime_files():
        source = path.read_text(encoding="utf-8")
        if legacy_runtime_literal.search(source) or static_authority_list.search(source):
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_control_plane_clients_keep_one_authority_and_provider_fallback_separate():
    agent = (ROOT / "ops" / "agent_host.py").read_text(encoding="utf-8")
    telegram = (ROOT / "ops" / "telegram_gateway.py").read_text(encoding="utf-8")
    dispatcher = (ROOT / "ops" / "kolibri-dispatch").read_text(encoding="utf-8")
    release = (ROOT / "ops" / "release_controller.py").read_text(encoding="utf-8")
    factory = (ROOT / "ops" / "factory_control.py").read_text(encoding="utf-8")

    assert "self.control_urls =" not in agent
    assert "self.control_urls =" not in telegram
    assert "for control_url in" not in agent
    assert "for control_url in" not in telegram
    assert '"fallback_nodes": []' in dispatcher
    assert "resolve_home_control_plane_url" in release
    assert "Provider failover" not in dispatcher
    assert "FABRIC_NODE_CATALOG" not in factory
    assert 'envelope["command_node"] = "home"' in factory


def test_systemd_binds_control_plane_to_home_identity_and_uses_mesh_discovery():
    units = {
        path.name: path.read_text(encoding="utf-8")
        for path in (ROOT / "ops" / "systemd").glob("*.service")
    }
    for source in units.values():
        assert "KOLIBRI_FACTORY_CONTROL_URL=" not in source

    factory = units["kolibri-factory-control.service"]
    assert "control_plane_endpoint.py --assert-local-home" in factory
    assert "KOLIBRI_MESH_MEMBERSHIP_MANIFEST=/var/lib/kolibri-mesh/peers.json" in factory
    for name in (
        "kolibri-agent-host.service",
        "kolibri-mesh-control-bridge.service",
        "kolibri-telegram-gateway.service",
    ):
        assert "KOLIBRI_MESH_MEMBERSHIP_MANIFEST=/var/lib/kolibri-mesh/peers.json" in units[name]
    agent = units["kolibri-agent-host.service"]
    assert "ExecStartPre=+/usr/bin/chgrp kolibri-agent /var/lib/kolibri-mesh/peers.json" in agent
    assert "ExecStartPre=+/usr/bin/chmod 0640 /var/lib/kolibri-mesh/peers.json" in agent
    assert "ReadWritePaths=/var/lib/kolibri-agent /var/lib/kolibri-mesh/peers.json" in agent


def test_new_node_bootstrap_installs_identical_agent_and_resolver_sources():
    provision = (ROOT / "scripts" / "provision-server.sh").read_text(encoding="utf-8")

    assert '"$SOURCE_ROOT/ops/agent_host.py"' in provision
    assert '"$SOURCE_ROOT/ops/mimo/kolibri-response-only.md"' in provision
    assert '"$SOURCE_ROOT/ops/control_plane_endpoint.py"' in provision
    assert '"$SOURCE_ROOT/ops/release_authority.py"' in provision
    assert '"$SOURCE_ROOT/ops/release_helper.py"' in provision
    assert '"$SOURCE_ROOT/ops/release_installer.py"' in provision
    assert "install -m755 /tmp/kolibri-agent-host /usr/local/bin/kolibri-agent-host" in provision
    assert (
        "install -m644 /tmp/kolibri-response-only.md "
        "/usr/local/lib/kolibri/mimo/kolibri-response-only.md"
    ) in provision
    assert "install -m644 /tmp/control_plane_endpoint.py /usr/local/lib/kolibri/control_plane_endpoint.py" in provision
    assert "install -m644 /tmp/release_authority.py /usr/local/lib/kolibri/release_authority.py" in provision
    assert "install -m644 /tmp/release_helper.py /usr/local/lib/kolibri/release_helper.py" in provision
    assert "install -m644 /tmp/release_installer.py /usr/local/lib/kolibri/release_installer.py" in provision
    assert "systemctl enable --now kolibri-release-helper.socket" in provision
    assert "heartbeat_agent.py" not in provision
    assert "dynamic Home from /var/lib/kolibri-mesh/peers.json" in provision


def test_installed_agent_host_can_import_resolver_from_the_same_directory(tmp_path):
    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    shutil.copy2(ROOT / "ops" / "agent_host.py", install_dir / "kolibri-agent-host")
    shutil.copy2(ROOT / "ops" / "control_plane_endpoint.py", install_dir / "control_plane_endpoint.py")
    shutil.copy2(ROOT / "ops" / "runner_access.py", install_dir / "runner_access.py")
    shutil.copy2(ROOT / "ops" / "release_authority.py", install_dir / "release_authority.py")
    shutil.copy2(ROOT / "ops" / "release_helper.py", install_dir / "release_helper.py")
    shutil.copy2(ROOT / "ops" / "release_installer.py", install_dir / "release_installer.py")
    membership = tmp_path / "peers.json"
    membership.write_text(
        '{"peers":{"home":{"node_id":"home","mesh_ip":"10.99.0.1"}}}',
        encoding="utf-8",
    )
    probe = (
        "import importlib.machinery, importlib.util, os, sys; "
        f"os.environ['KOLIBRI_MESH_MEMBERSHIP_MANIFEST']={str(membership)!r}; "
        f"sys.path.insert(0, {str(install_dir)!r}); "
        f"loader=importlib.machinery.SourceFileLoader('installed_agent_host', {str(install_dir / 'kolibri-agent-host')!r}); "
        "spec=importlib.util.spec_from_loader(loader.name, loader); "
        "module=importlib.util.module_from_spec(spec); loader.exec_module(module); "
        "print(module.resolve_home_control_plane_url())"
    )

    completed = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "http://10.99.0.1:9101"


def test_deploy_compatibility_entrypoint_is_api_only_and_legacy_targets_fail_closed():
    deploy = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    dispatcher = (ROOT / "ops" / "kolibri-dispatch").read_text(encoding="utf-8")

    assert not re.search(r"\b(?:ssh|scp|rsync)\b", deploy, flags=re.IGNORECASE)
    assert "ops/release_controller.py" in deploy
    assert "legacy_direct_deploy_disabled" in deploy
    assert 'subprocess.run(["ssh"' not in dispatcher
    assert 'subprocess.run(["scp"' not in dispatcher
    assert "legacy_direct_ssh_dispatch_disabled" in dispatcher
