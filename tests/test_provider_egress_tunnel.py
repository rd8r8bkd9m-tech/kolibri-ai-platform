from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops import provider_egress_tunnel as tunnel


ROOT = Path(__file__).resolve().parents[1]


def executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def signed_case(tmp_path: Path):
    membership = tmp_path / "peers.json"
    membership.write_text(json.dumps({
        "schema_version": 1,
        "epoch": 2,
        "cluster_id": "test",
        "peers": {
            "home": {"node_id": "home", "mesh_ip": "10.99.0.1"},
            "egress-fast": {"node_id": "egress-fast", "mesh_ip": "10.99.0.22"},
        },
    }), encoding="utf-8")
    identity = tmp_path / "provider-egress-key"
    identity.write_text("private-material-not-read-by-launcher", encoding="utf-8")
    identity.chmod(0o600)
    known_hosts = tmp_path / "known-hosts"
    known_hosts.write_text("hashed-or-public-host-key", encoding="utf-8")
    allowed = tmp_path / "allowed-signers"
    allowed.write_text("owner ssh-ed25519 public-material", encoding="utf-8")
    signature = tmp_path / "provider-egress.json.sig"
    signature.write_text(
        "-----BEGIN SSH SIGNATURE-----\ntest\n-----END SSH SIGNATURE-----\n",
        encoding="ascii",
    )
    config = tmp_path / "provider-egress.json"
    payload = {
        "schema_version": tunnel.SCHEMA_VERSION,
        "egress_node_id": "egress-fast",
        "ssh_user": "egress",
        "ssh_port": 22,
        "identity_file": str(identity),
        "known_hosts_file": str(known_hosts),
        "listen_host": "127.0.0.1",
        "listen_port": 19090,
        "signer_identity": "owner",
    }
    config.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return config, signature, allowed, membership, identity, known_hosts


def test_signed_selector_resolves_current_mesh_endpoint_without_static_ip(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config, signature, allowed, membership, identity, known_hosts = signed_case(tmp_path)
    ssh = executable(tmp_path / "ssh")
    ssh_keygen = executable(tmp_path / "ssh-keygen")
    calls = []

    def verify(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(tunnel.subprocess, "run", verify)
    loaded = tunnel.load_config(
        config_path=config,
        signature_path=signature,
        allowed_signers=allowed,
        membership_path=membership,
        ssh_keygen=ssh_keygen,
        local_addresses=["10.99.0.1/24"],
    )
    command = tunnel.ssh_command(loaded, ssh)

    assert loaded.egress_node_id == "egress-fast"
    assert loaded.endpoint == "10.99.0.22"
    assert command[-1] == "egress@10.99.0.22"
    assert command[command.index("-D") + 1] == "127.0.0.1:19090"
    assert "StrictHostKeyChecking=yes" in command
    assert f"UserKnownHostsFile={known_hosts}" in command
    assert command[command.index("-i") + 1] == str(identity)
    assert calls[0][0][calls[0][0].index("-n") + 1] == tunnel.SIGNATURE_NAMESPACE
    assert calls[0][1]["input"] == config.read_bytes()
    assert "private-material" not in str(command)


def test_unsigned_or_noncanonical_config_fails_closed(tmp_path: Path, monkeypatch) -> None:
    config, signature, allowed, membership, _identity, _known_hosts = signed_case(tmp_path)
    ssh_keygen = executable(tmp_path / "ssh-keygen")
    monkeypatch.setattr(
        tunnel.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )
    with pytest.raises(tunnel.ProviderEgressError, match="signature_invalid"):
        tunnel.load_config(
            config_path=config,
            signature_path=signature,
            allowed_signers=allowed,
            membership_path=membership,
            ssh_keygen=ssh_keygen,
            local_addresses=["10.99.0.1/24"],
        )

    config.write_text(json.dumps(json.loads(config.read_text()), indent=2), encoding="utf-8")
    with pytest.raises(tunnel.ProviderEgressError, match="config_invalid"):
        tunnel.load_config(
            config_path=config,
            signature_path=signature,
            allowed_signers=allowed,
            membership_path=membership,
            ssh_keygen=ssh_keygen,
            local_addresses=["10.99.0.1/24"],
        )


def test_systemd_contract_is_provider_only_dynamic_and_rollbackable() -> None:
    tunnel_unit = (ROOT / "ops/systemd/kolibri-provider-egress-tunnel.service").read_text(
        encoding="utf-8"
    )
    proxy_unit = (ROOT / "ops/systemd/kolibri-provider-egress-proxy.service").read_text(
        encoding="utf-8"
    )
    agent_dropin = (ROOT / "ops/systemd/kolibri-agent-host-provider-egress.conf").read_text(
        encoding="utf-8"
    )
    combined = tunnel_unit + proxy_unit + agent_dropin + (
        ROOT / "ops/provider_egress_tunnel.py"
    ).read_text(encoding="utf-8")

    assert "assert_local_home_control_plane" in combined
    assert "egress_node_id" in combined
    assert "canonical_mesh_manifest" in combined
    assert "--fallback-socks-host 127.0.0.1" in proxy_unit
    assert "--mark 0x66" in proxy_unit
    assert "provider_egress_preflight.py" in proxy_unit
    assert "AmbientCapabilities=CAP_NET_RAW" in proxy_unit
    assert "IPAddressDeny=any" not in proxy_unit
    assert "Requires=kolibri-provider-egress-tunnel.service" not in proxy_unit
    assert "KOLIBRI_PROVIDER_PROXY_URL=http://127.0.0.1:18080" in agent_dropin
    assert "Wants=kolibri-provider-egress-proxy.service" in agent_dropin
    assert "HTTPS_PROXY=" not in agent_dropin
    assert "10.99.0.0/24" not in tunnel_unit  # NO_PROXY belongs to provider children only.
    for unaffected in (
        "kolibri-factory-control.service",
        "kolibri-backend-home-release.conf",
        "kolibri-mesh-registry.service",
    ):
        source = (ROOT / "ops/systemd" / unaffected).read_text(encoding="utf-8")
        assert "KOLIBRI_PROVIDER_PROXY_URL" not in source
        assert "HTTPS_PROXY=" not in source
    for forbidden in ("78.17.4.108", "217.", "kolibri-main", "kolibri-primary"):
        assert forbidden not in combined
