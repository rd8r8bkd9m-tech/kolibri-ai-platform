from __future__ import annotations

import base64
import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROLLOUT = ROOT / "scripts" / "rollout-mesh-peer-persistence.sh"
ROUTE_REPAIR = ROOT / "scripts" / "repair-mesh-route-collision.sh"
UNIT = ROOT / "ops" / "systemd" / "kolibri-mesh-apply-peers.service"


def _manifest(path: Path) -> Path:
    peers: dict[str, dict[str, object]] = {}
    names = ["home", *(f"node{i:02d}" for i in range(1, 21))]
    for index, node_id in enumerate(names, start=1):
        mesh_ip = f"10.99.0.{index}"
        peers[mesh_ip] = {
            "node_id": node_id,
            "mesh_ip": mesh_ip,
            "public_key": base64.b64encode(bytes([index]) * 32).decode("ascii"),
            "endpoint": f"203.0.113.{index}:51830",
            "revision": 1,
        }
    path.write_text(json.dumps({"peers": peers}), encoding="utf-8")
    return path


def _fake_transport(directory: Path) -> tuple[Path, Path]:
    marker = directory / "scp-was-called"
    ssh = directory / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "case \" $* \" in\n"
        "  *\" /bin/bash -s \"*)\n"
        "    cat >/dev/null\n"
        "    echo 'node=node01 fragments=21 runtime_peers=1 fresh_handshakes=1 unit_load=not-found unit_enabled=not-found'\n"
        "    ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    scp = directory / "scp"
    scp.write_text(
        f"#!/bin/sh\nprintf called >{marker!s}\nexit 91\n", encoding="utf-8"
    )
    scp.chmod(0o755)
    return directory, marker


def test_peer_apply_unit_is_pulled_by_boot_and_each_wireguard_start():
    source = UNIT.read_text(encoding="utf-8")

    assert "Before=kolibri-mesh-registry.service" in source
    assert "After=wg-quick@wg-kolibri.service" in source
    assert "Requires=wg-quick@wg-kolibri.service" in source
    assert "PartOf=wg-quick@wg-kolibri.service" in source
    assert "WantedBy=multi-user.target wg-quick@wg-kolibri.service" in source


def test_persistence_rollout_is_manifest_driven_reversible_and_never_restarts_wg():
    source = ROLLOUT.read_text(encoding="utf-8")

    assert "APPLY=false" in source
    assert "--apply" in source
    assert "--only-node" in source
    assert "--canary" in source
    assert ".peers[]" in source
    assert "sha256sum -c checksums.sha256" in source
    assert "/var/backups/kolibri/mesh-peer-persistence/" in source
    assert "wg showconf wg-kolibri" in source
    assert "wg syncconf wg-kolibri" in source
    assert "rollback_node" in source
    assert "fresh_handshakes" in source
    assert "ActiveEnterTimestampMonotonic" in source
    assert "systemctl restart kolibri-mesh-apply-peers.service" in source
    assert "systemctl restart wg-quick" not in source
    assert "wg-quick down" not in source
    assert "StrictHostKeyChecking=no" not in source
    assert re.search(r"\bprimary\b", source) is None
    assert re.search(r"\bmain\b", source) is None


def test_persistence_rollout_default_dry_run_does_not_copy(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _, marker = _fake_transport(fake_bin)
    manifest = _manifest(tmp_path / "peers.json")
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    completed = subprocess.run(
        [str(ROLLOUT), "--manifest", str(manifest), "--only-node", "node01"],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr
    assert "mode=dry-run" in completed.stdout
    assert "dry_run_complete" in completed.stdout
    assert not marker.exists()


def test_route_collision_repair_is_single_token_guarded_and_reversible():
    source = ROUTE_REPAIR.read_text(encoding="utf-8")

    assert "APPLY=false" in source
    assert 'CONFLICT_CIDR=""' in source
    assert 'ROUTE_OWNER=""' in source
    assert "--conflict-cidr" in source
    assert "--route-owner" in source
    assert "192.168.88.0/24" not in source
    assert "kgmhomeexit0" not in source
    assert 'removed != 1' in source
    assert 'hits" -eq 1' in source
    assert "os.replace(temporary, path)" in source
    assert "/var/backups/kolibri/mesh-route-collision/" in source
    assert "rollback_remote" in source
    assert "systemctl start wg-quick@wg-kolibri.service" in source
    assert "/usr/local/sbin/kolibri-mesh-apply-peers" in source
    assert "ip route del" not in source
    assert "ip route delete" not in source
    assert "StrictHostKeyChecking=no" not in source


def test_route_collision_repair_default_dry_run_does_not_apply(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _, marker = _fake_transport(fake_bin)
    manifest = _manifest(tmp_path / "peers.json")
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    completed = subprocess.run(
        [
            str(ROUTE_REPAIR),
            "--manifest",
            str(manifest),
            "--node",
            "node01",
            "--conflict-cidr",
            "192.0.2.0/24",
            "--route-owner",
            "test-exit0",
        ],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr
    assert "mode=dry-run" in completed.stdout
    assert "dry_run_complete" in completed.stdout
    assert not marker.exists()


def test_mesh_repair_scripts_parse_as_bash():
    for script in (ROLLOUT, ROUTE_REPAIR):
        completed = subprocess.run(
            ["bash", "-n", str(script)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
