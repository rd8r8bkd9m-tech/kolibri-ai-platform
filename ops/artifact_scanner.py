#!/usr/bin/env python3
"""Read-only artifact inventory over dynamically discovered fleet members.

This is an owner/operator diagnostic, not a factory worker transport.  The
target set comes from the canonical Home Control Plane registration snapshot;
mesh addresses come from the replicated membership manifest.  The scanner
fails closed when either source cannot identify a requested server and never
falls back to a historical hostname or SSH alias.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

try:
    from ops.factory_registry import AssetRecord, load_registered_servers
except ImportError:  # direct execution from ops/
    from factory_registry import AssetRecord, load_registered_servers


@dataclass
class ArtifactRecord:
    artifact_id: str
    server_node_id: str
    kind: str  # proof, deployment, model, config, log, backup
    path: str
    size_bytes: int
    created_at: str
    checksum: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ArtifactScanResult:
    server_node_id: str
    artifacts: list[ArtifactRecord]
    disk_usage_gb: float
    services_running: list[str]
    scan_timestamp: str

    def to_dict(self) -> dict:
        return {
            "server_node_id": self.server_node_id,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "disk_usage_gb": self.disk_usage_gb,
            "services_running": self.services_running,
            "scan_timestamp": self.scan_timestamp,
        }


SCAN_PATHS = [
    ("/tmp/PROOF*", "proof"),
    ("/tmp/kolibri-*", "deployment"),
    ("/opt/kolibri-*/", "deployment"),
    ("/opt/kolibri-models/", "model"),
    ("/srv/kolibri/data/models/", "model"),
    ("/etc/kolibri/", "config"),
    ("/var/log/kolibri*", "log"),
]


def ssh_exec(host: str, command: str, timeout: int = 10) -> str | None:
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", host, command],
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def scan_server(server_id: str, ssh_alias: str) -> ArtifactScanResult:
    artifacts: list[ArtifactRecord] = []
    now = datetime.now(timezone.utc).isoformat()

    # Disk usage
    disk_raw = ssh_exec(ssh_alias, "df -BG / | tail -1 | awk '{print $3}'")
    disk_gb = float(disk_raw.rstrip("G")) if disk_raw else 0.0

    # Running services
    services_raw = ssh_exec(ssh_alias, "systemctl list-units --type=service --state=running --no-legend | awk '{print $1}' | head -20")
    services = services_raw.split("\n") if services_raw else []

    # Scan paths
    for pattern, kind in SCAN_PATHS:
        files_raw = ssh_exec(ssh_alias, f"find {pattern} -maxdepth 1 -type f 2>/dev/null | head -10")
        if not files_raw:
            continue
        for fpath in files_raw.split("\n"):
            if not fpath:
                continue
            quoted_path = shlex.quote(fpath)
            size_raw = ssh_exec(ssh_alias, f"stat -c %s -- {quoted_path} 2>/dev/null")
            size = int(size_raw) if size_raw else 0
            checksum_raw = ssh_exec(ssh_alias, f"sha256sum -- {quoted_path} 2>/dev/null | cut -d' ' -f1")
            checksum = checksum_raw[:16] if checksum_raw else "unknown"
            artifact_id = f"{server_id}:{kind}:{checksum[:8]}"
            artifacts.append(ArtifactRecord(
                artifact_id=artifact_id,
                server_node_id=server_id,
                kind=kind,
                path=fpath,
                size_bytes=size,
                created_at=now,
                checksum=checksum,
            ))

    return ArtifactScanResult(
        server_node_id=server_id,
        artifacts=artifacts,
        disk_usage_gb=disk_gb,
        services_running=services,
        scan_timestamp=now,
    )


def _mesh_ssh_target(record: AssetRecord) -> str:
    raw_address = str(record.internal_ip or "").strip()
    try:
        address = ipaddress.ip_address(raw_address)
    except ValueError as exc:
        raise RuntimeError(f"mesh_address_missing_or_invalid:{record.node_id}") from exc
    if (
        address.version != 4
        or not address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
    ):
        raise RuntimeError(f"mesh_address_missing_or_invalid:{record.node_id}")
    return str(address)


def discover_scan_targets(
    *,
    control_url: str | None = None,
    manifest_path: str | Path | None = None,
    server_id: str | None = None,
    loader: Callable[..., list[AssetRecord]] | None = None,
) -> list[tuple[str, str]]:
    """Return ``(node_id, mesh_ip)`` from Home registration + manifest."""

    if server_id and not re.fullmatch(r"[A-Za-z0-9._-]+", server_id):
        raise RuntimeError("server_id_invalid")
    membership_loader = loader or load_registered_servers
    records = membership_loader(control_url, manifest_path=manifest_path)
    selected = [record for record in records if not server_id or record.node_id == server_id]
    if server_id and not selected:
        raise RuntimeError(f"server_not_registered:{server_id}")
    if not selected:
        raise RuntimeError("no_registered_servers")
    return [(record.node_id, _mesh_ssh_target(record)) for record in selected]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", help="scan one registered node id")
    parser.add_argument("--manifest", help="replicated mesh membership manifest")
    parser.add_argument("--control-url", help="explicit canonical Home Control Plane URL")
    args = parser.parse_args(argv)

    try:
        servers = discover_scan_targets(
            control_url=args.control_url,
            manifest_path=args.manifest,
            server_id=args.server,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"artifact_scan_target_discovery_failed: {exc}\n")

    results = []
    for server_id, ssh_alias in servers:
        print(f"Scanning {server_id} ({ssh_alias})...", file=sys.stderr)
        result = scan_server(server_id, ssh_alias)
        results.append(result)
        print(
            f"  Found {len(result.artifacts)} artifacts, {result.disk_usage_gb}GB used, "
            f"{len(result.services_running)} services",
            file=sys.stderr,
        )

    output = [r.to_dict() for r in results]
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
