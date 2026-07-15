#!/usr/bin/env python3
"""World Model — dependency graph and cause-effect reasoning."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, asdict

CONTROL_PLANE = "http://192.168.88.210:9101"


@dataclass
class Dependency:
    source: str
    target: str
    dependency_type: str  # "requires" | "feeds" | "monitors"

    def to_dict(self) -> dict:
        return asdict(self)


_graph: dict[str, list[Dependency]] = {}


def _request(method: str, url: str, data: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def add_dependency(source: str, target: str, dep_type: str = "requires") -> Dependency:
    dep = Dependency(source=source, target=target, dependency_type=dep_type)
    if source not in _graph:
        _graph[source] = []
    _graph[source].append(dep)
    return dep


def get_dependencies(node: str) -> list[Dependency]:
    return _graph.get(node, [])


def get_dependents(node: str) -> list[Dependency]:
    deps = []
    for source, targets in _graph.items():
        for dep in targets:
            if dep.target == node:
                deps.append(dep)
    return deps


def get_graph() -> dict:
    return {k: [d.to_dict() for d in v] for k, v in _graph.items()}


def predict_impact(node: str) -> list[str]:
    impacted = []
    queue = [node]
    while queue:
        current = queue.pop(0)
        for dep in get_dependents(current):
            if dep.target not in impacted:
                impacted.append(dep.target)
                queue.append(dep.target)
    return impacted


def explain_event(event: str) -> dict:
    return {
        "event": event,
        "possible_causes": [d.source for d in get_dependencies(event)],
        "possible_effects": predict_impact(event),
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: world_model.py <graph|impact|explain> [node]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "graph":
        print(json.dumps(get_graph(), indent=2))
    elif action == "impact" and len(sys.argv) > 2:
        impacted = predict_impact(sys.argv[2])
        print(f"  Impact of {sys.argv[2]}: {impacted}")
    elif action == "explain" and len(sys.argv) > 2:
        print(json.dumps(explain_event(sys.argv[2]), indent=2))
