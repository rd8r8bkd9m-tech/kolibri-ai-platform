#!/usr/bin/env python3
"""Kolibri Artifact Scanner — сканирование артефактов на серверах через SSH.

Запуск: python3 ops/artifact_scanner.py --server home
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


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
            size_raw = ssh_exec(ssh_alias, f"stat -c %s {fpath} 2>/dev/null")
            size = int(size_raw) if size_raw else 0
            checksum_raw = ssh_exec(ssh_alias, f"sha256sum {fpath} 2>/dev/null | cut -d' ' -f1")
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


def main():
    servers = [
        ("home", "kolibri-home"),
        ("main", "kolibri-main"),
        ("primary", "kolibri-primary-codex"),
        ("uiap", "kolibri-uiap"),
        ("qjns", "kolibri-qjns"),
        ("9fts", "kolibri-9fts"),
        ("new", "kolibri-new"),
    ]

    if len(sys.argv) > 1 and sys.argv[1] == "--server":
        server_id = sys.argv[2]
        servers = [(s, a) for s, a in servers if s == server_id]

    results = []
    for server_id, ssh_alias in servers:
        print(f"Scanning {server_id} ({ssh_alias})...")
        result = scan_server(server_id, ssh_alias)
        results.append(result)
        print(f"  Found {len(result.artifacts)} artifacts, {result.disk_usage_gb}GB used, {len(result.services_running)} services")

    # Output
    output = [r.to_dict() for r in results]
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
