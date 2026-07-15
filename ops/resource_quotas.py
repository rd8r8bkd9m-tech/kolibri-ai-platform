#!/usr/bin/env python3
"""Resource Quotas — CPU/RAM/Disk limits per node."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, asdict

CONTROL_PLANE = "http://192.168.88.210:9101"


@dataclass
class Quota:
    node_id: str
    cpu_cores: float
    ram_gb: float
    disk_gb: float
    network_mbps: int

    def to_dict(self) -> dict:
        return asdict(self)


_quotas: dict[str, Quota] = {}


def _request(method: str, url: str, data: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def set_quota(node_id: str, cpu: float = 2, ram: float = 4, disk: float = 50, network: int = 100) -> Quota:
    quota = Quota(node_id=node_id, cpu_cores=cpu, ram_gb=ram, disk_gb=disk, network_mbps=network)
    _quotas[node_id] = quota
    return quota


def get_quota(node_id: str) -> Quota | None:
    return _quotas.get(node_id)


def get_usage(node_id: str) -> dict:
    return _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": node_id,
        "command": "free -g | awk '/Mem:/{print $3\"/\"$2}' && df -h / | awk 'NR==2{print $3\"/\"$2}' && nproc",
        "objective": f"Get resource usage on {node_id}",
        "kind": "read_only_probe",
    })


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: resource_quotas.py <list|set|usage> [node_id] [cpu] [ram] [disk]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "list":
        for nid, q in _quotas.items():
            print(f"  {nid}: CPU={q.cpu_cores} RAM={q.ram_gb}GB Disk={q.disk_gb}GB Net={q.network_mbps}Mbps")
    elif action == "set" and len(sys.argv) > 2:
        node_id = sys.argv[2]
        cpu = float(sys.argv[3]) if len(sys.argv) > 3 else 2
        ram = float(sys.argv[4]) if len(sys.argv) > 4 else 4
        disk = float(sys.argv[5]) if len(sys.argv) > 5 else 50
        q = set_quota(node_id, cpu, ram, disk)
        print(f"  Quota set for {node_id}: {q.to_dict()}")
    elif action == "usage" and len(sys.argv) > 2:
        print(json.dumps(get_usage(sys.argv[2]), indent=2))
