#!/usr/bin/env python3
"""Service Discovery — DNS-like registry for fleet services."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, asdict

CONTROL_PLANE = "http://192.168.88.210:9101"


@dataclass
class Service:
    service: str
    node_id: str
    url: str
    health: str
    capabilities: list[str]


_services: dict[str, Service] = {}


def _request(method: str, url: str, data: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def register(service: Service) -> None:
    _services[service.service] = service
    _request("POST", f"{CONTROL_PLANE}/v1/tasks", {
        "node_id": service.node_id,
        "command": f"echo 'Service {service.service} registered at {service.url}'",
        "objective": f"Register {service.service}",
        "kind": "read_only_probe",
    })


def deregister(service_name: str) -> None:
    _services.pop(service_name, None)


def find(service_name: str) -> Service | None:
    return _services.get(service_name)


def list_services() -> list[Service]:
    return list(_services.values())


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: service_discovery.py <list|find> [service_name]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "list":
        services = list_services()
        for s in services:
            print(f"  {s.service}: {s.url} ({s.node_id})")
    elif action == "find" and len(sys.argv) > 2:
        svc = find(sys.argv[2])
        if svc:
            print(json.dumps(asdict(svc), indent=2))
        else:
            print(f"Service {sys.argv[2]} not found")
