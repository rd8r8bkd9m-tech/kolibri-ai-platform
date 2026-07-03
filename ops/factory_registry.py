#!/usr/bin/env python3
"""Canonical Kolibri Factory registry helpers.

This module is intentionally standard-library only so the control plane,
dispatcher, tests and docs tooling can share the same truth without importing
runtime services or leaking environment values.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


SOURCE_OF_TRUTH_VERSION = "2026-07-03-p0"


CANONICAL_NODE_REGISTRY: dict[str, dict[str, Any]] = {
    "home": {
        "node_id": "home",
        "role": "command_node_gateway",
        "record_type": "hybrid_node",
        "display_name": "Svyaznoy",
        "internal_ips": ["10.99.0.1"],
        "external_ips": ["178.207.11.90"],
        "api_paths": ["fabric_api", "fallback_relay"],
        "fallback_eligible": True,
        "services": ["home_gateway", "mesh_gateway"],
    },
    "main": {
        "node_id": "main",
        "role": "control_plane",
        "record_type": "hybrid_node",
        "display_name": "Director",
        "internal_ips": ["10.99.0.2"],
        "external_ips": ["104.253.43.117"],
        "api_paths": ["fabric_api", "control_plane_api", "artifact_api"],
        "fallback_eligible": True,
        "services": ["control_plane", "agent_host"],
    },
    "primary-candidate": {
        "node_id": "primary-candidate",
        "role": "primary_control_plane_candidate",
        "record_type": "hybrid_node",
        "display_name": "Primary Candidate",
        "internal_ips": ["10.99.0.10"],
        "external_ips": ["78.17.4.108"],
        "api_paths": ["fabric_api", "control_plane_api", "artifact_api"],
        "fallback_eligible": True,
        "services": ["control_plane", "frontend_dev", "frontend_preview", "backend_staging", "mesh_bridge"],
    },
    "uiap": {
        "node_id": "uiap",
        "role": "knowledge_model_node",
        "record_type": "execution_node",
        "display_name": "Knowledge",
        "internal_ips": ["10.99.0.3"],
        "external_ips": ["31.57.26.151"],
        "api_paths": ["fabric_api", "fallback_relay"],
        "fallback_eligible": True,
        "services": ["agent_host"],
    },
    "qjns": {
        "node_id": "qjns",
        "role": "remote_agent",
        "record_type": "execution_node",
        "display_name": "Tester",
        "internal_ips": ["10.99.0.4"],
        "external_ips": ["217.60.63.97"],
        "api_paths": ["fabric_api", "agent_host_api", "fallback_relay"],
        "fallback_eligible": True,
        "services": ["agent_host"],
    },
    "9fts": {
        "node_id": "9fts",
        "role": "implementation_model_node",
        "record_type": "execution_node",
        "display_name": "Engineer",
        "internal_ips": ["10.99.0.5"],
        "external_ips": ["94.183.235.154"],
        "api_paths": ["fabric_api", "agent_host_api", "model_node_api", "fallback_relay"],
        "fallback_eligible": True,
        "services": ["agent_host", "model_runtime"],
    },
    "new": {
        "node_id": "new",
        "role": "review_agent",
        "record_type": "execution_node",
        "display_name": "Reviewer",
        "internal_ips": ["10.99.0.6"],
        "external_ips": ["109.248.161.39"],
        "api_paths": ["fabric_api", "agent_host_api", "fallback_relay"],
        "fallback_eligible": True,
        "services": ["agent_host"],
    },
    "server-kfrm": {
        "node_id": "server-kfrm",
        "role": "reserve_server",
        "record_type": "physical_server",
        "display_name": "Server KFRM",
        "internal_ips": [],
        "external_ips": ["217.60.63.31"],
        "api_paths": ["fallback_relay"],
        "fallback_eligible": False,
        "services": [],
    },
    "reserve242": {
        "node_id": "reserve242",
        "role": "reserve_server",
        "record_type": "physical_server",
        "display_name": "Reserve 242",
        "internal_ips": [],
        "external_ips": ["31.57.26.242"],
        "api_paths": ["fallback_relay"],
        "fallback_eligible": False,
        "services": [],
    },
    "highload": {
        "node_id": "highload",
        "role": "reserve_server",
        "record_type": "physical_server",
        "display_name": "Highload",
        "internal_ips": [],
        "external_ips": ["45.38.139.182"],
        "api_paths": ["fallback_relay"],
        "fallback_eligible": False,
        "services": [],
    },
    "paris": {
        "node_id": "paris",
        "role": "reserve_server",
        "record_type": "physical_server",
        "display_name": "Paris",
        "internal_ips": [],
        "external_ips": ["95.182.83.60"],
        "api_paths": ["fallback_relay"],
        "fallback_eligible": False,
        "services": [],
    },
}

for index, external_ip in enumerate(
    [
        "31.57.27.128",
        "213.232.204.223",
        "188.130.206.204",
        "31.59.41.146",
        "31.56.196.10",
        "45.39.33.252",
        "46.8.225.34",
        "31.59.105.200",
        "95.182.84.254",
        "217.60.38.191",
    ],
    start=1,
):
    node_id = f"agent-{index:02d}"
    CANONICAL_NODE_REGISTRY[node_id] = {
        "node_id": node_id,
        "role": "reserve_agent",
        "record_type": "physical_server",
        "display_name": f"Agent {index:02d}",
        "internal_ips": [],
        "external_ips": [external_ip],
        "api_paths": ["fallback_relay"],
        "fallback_eligible": False,
        "services": [],
    }
    if node_id == "agent-10":
        CANONICAL_NODE_REGISTRY[node_id].update(
            {
                "lifecycle": "quarantined",
                "network_status_override": "provider_network_unreachable",
                "repair_required": "verify provider console or retire after owner approval",
            }
        )


def _ssh_access_for_node(node_id: str, data: dict[str, Any]) -> dict[str, Any]:
    internal_ips = data.get("internal_ips") or []
    external_ips = data.get("external_ips") or []
    if node_id == "home":
        return {
            "mode": "direct_internal",
            "target": internal_ips[0],
            "user": "ladik",
            "jump": None,
            "identity": "kolibri_home_repair_20260703_ed25519",
            "fallback_target": external_ips[0] if external_ips else None,
        }
    if node_id == "main":
        return {
            "mode": "internal_via_home",
            "target": internal_ips[0],
            "user": "root",
            "jump": "kolibri-home",
            "identity": "kolibri_ai_platform_deploy_ed25519",
            "fallback_target": external_ips[0] if external_ips else None,
        }
    if internal_ips:
        jump = "kolibri-home" if node_id == "qjns" else "kolibri-main"
        return {
            "mode": f"internal_via_{jump.removeprefix('kolibri-')}",
            "target": internal_ips[0],
            "user": "root",
            "jump": jump,
            "identity": "kolibri_ai_platform_deploy_ed25519",
            "fallback_target": external_ips[0] if external_ips else None,
        }
    return {
        "mode": "external_via_main",
        "target": external_ips[0] if external_ips else None,
        "user": "root",
        "jump": "kolibri-main",
        "identity": "kolibri_ai_platform_deploy_ed25519",
        "fallback_target": None,
    }


for _node_id, _node_data in CANONICAL_NODE_REGISTRY.items():
    _node_data["ssh_access"] = _ssh_access_for_node(_node_id, _node_data)


NODE_ALIAS_MAP: dict[str, str] = {
    "home-live": "home",
    "primary": "primary-candidate",
    "direct": "primary-candidate",
    "rag": "uiap",
    "tools": "qjns",
    "inference": "9fts",
    "worker-backup": "new",
}


CAPABILITY_REGISTRY: dict[str, dict[str, Any]] = {
    "implementation": {
        "aliases": ["generic_implementation"],
        "required_runner": None,
        "allowed_node_types": ["execution_node", "hybrid_node", "logical_worker"],
        "safety": "requires real implementation capability or explicit generic implementation capability",
    },
    "generic_implementation": {
        "aliases": ["implementation"],
        "required_runner": None,
        "allowed_node_types": ["execution_node", "hybrid_node", "logical_worker"],
        "safety": "does not imply a specific runner",
    },
    "devops": {
        "aliases": ["permission:*"],
        "required_runner": None,
        "allowed_node_types": ["hybrid_node", "execution_node", "logical_worker"],
        "safety": "permission:* only satisfies devops when policy allows privileged work",
    },
    "github_review": {
        "aliases": ["review", "generic_review"],
        "required_runner": None,
        "allowed_node_types": ["execution_node", "logical_worker"],
        "safety": "review capability must be real; no fake reviewer fallback",
    },
    "review": {
        "aliases": ["generic_review", "github_review"],
        "required_runner": None,
        "allowed_node_types": ["execution_node", "logical_worker"],
        "safety": "review capability must be real",
    },
    "runner:codex": {
        "aliases": ["runner_codex", "codex_runner"],
        "required_runner": "codex",
        "allowed_node_types": ["hybrid_node", "logical_worker"],
        "safety": "requires actual Codex runner availability",
    },
    "runner:mimo": {
        "aliases": ["runner_mimo", "mimo_runner"],
        "required_runner": "mimo",
        "allowed_node_types": ["execution_node", "hybrid_node", "logical_worker"],
        "safety": "requires actual MIMO runner availability",
    },
    "runner:api": {
        "aliases": ["runner_api", "api_runner"],
        "required_runner": "api",
        "allowed_node_types": ["hybrid_node", "logical_worker"],
        "safety": "requires authenticated API runner",
    },
}

CAPABILITY_ALIASES: dict[str, set[str]] = {
    name: {str(alias) for alias in data.get("aliases", [])}
    for name, data in CAPABILITY_REGISTRY.items()
}


RUNNER_REGISTRY: dict[str, dict[str, Any]] = {
    "codex": {
        "capability": "runner:codex",
        "task_types": ["owner_remote_task", "review_pr", "read_only_probe"],
        "health_check": "node runners.codex.status == available",
        "failure_modes": ["runner_access_denied", "runner_auth_blocked", "runner_unavailable"],
        "fallback": "mimo or api only when task policy allows",
    },
    "mimo": {
        "capability": "runner:mimo",
        "task_types": ["owner_remote_task", "generic_implementation"],
        "health_check": "node runners.mimo.status == available",
        "failure_modes": ["runner_auth_blocked", "runner_unavailable"],
        "fallback": "codex or api only when task policy allows",
    },
    "api": {
        "capability": "runner:api",
        "task_types": ["owner_remote_task", "fabric_api"],
        "health_check": "node runners.api.status == available",
        "failure_modes": ["auth_failed", "api_unreachable"],
        "fallback": "fabric relay",
    },
    "local_llm": {
        "capability": "runner:local_llm",
        "task_types": ["model_task"],
        "health_check": "model runtime health endpoint",
        "failure_modes": ["model_runtime_unavailable"],
        "fallback": "blocked until authenticated model node is online",
    },
    "review": {
        "capability": "review",
        "task_types": ["review_pr"],
        "health_check": "review capability and runner status",
        "failure_modes": ["missing_capability", "runner_unavailable"],
        "fallback": "github_review alias only on capable node",
    },
    "qa": {
        "capability": "qa",
        "task_types": ["qa", "test"],
        "health_check": "qa capability",
        "failure_modes": ["missing_capability"],
        "fallback": "capability-compatible fallback if policy allows",
    },
    "generic_implementation": {
        "capability": "generic_implementation",
        "task_types": ["owner_remote_task"],
        "health_check": "implementation or generic implementation capability",
        "failure_modes": ["missing_capability"],
        "fallback": "capability-compatible fallback if policy allows",
    },
}


SERVICE_ENDPOINT_REGISTRY: dict[str, dict[str, Any]] = {
    "control_plane": {
        "node": "primary-candidate",
        "canonical_url": "http://10.99.0.10:9101",
        "bind_address": "0.0.0.0",
        "port": 9101,
        "systemd_unit": "kolibri-factory-control.service",
        "health_endpoint": "/v1/health",
        "expected_status": "online",
        "fallback": "http://10.99.0.2:9101",
    },
    "backend_staging": {
        "node": "primary-candidate",
        "canonical_url": "http://10.99.0.10:19131",
        "bind_address": "0.0.0.0",
        "port": 19131,
        "systemd_unit": "kolibri-staging-pr31-backend.service",
        "health_endpoint": "/api/health",
        "expected_status": "online",
        "fallback": "",
    },
    "frontend_preview": {
        "node": "primary-candidate",
        "canonical_url": "http://10.99.0.10:19132",
        "bind_address": "0.0.0.0",
        "port": 19132,
        "systemd_unit": "kolibri-staging-pr31-frontend.service",
        "health_endpoint": "/",
        "expected_status": "online",
        "fallback": "frontend_dev",
    },
    "frontend_dev": {
        "node": "primary-candidate",
        "canonical_url": "http://10.99.0.10:5173",
        "bind_address": "0.0.0.0",
        "port": 5173,
        "systemd_unit": "kolibri-frontend-5173.service",
        "health_endpoint": "/",
        "expected_status": "online_when_dev_server_running",
        "fallback": "frontend_preview",
    },
    "mesh_bridge": {
        "node": "primary-candidate",
        "canonical_url": "http://10.99.0.10:9101",
        "bind_address": "0.0.0.0",
        "port": 9101,
        "systemd_unit": "kolibri-mesh-control-bridge.service",
        "health_endpoint": "/v1/health",
        "expected_status": "online",
        "fallback": "control_plane",
    },
    "redis": {
        "node": "primary-candidate",
        "canonical_url": "redis://127.0.0.1:6379",
        "bind_address": "127.0.0.1",
        "port": 6379,
        "systemd_unit": "redis-server.service",
        "health_endpoint": "PING",
        "expected_status": "online",
        "fallback": "",
    },
}

PORT_REGISTRY: dict[int, dict[str, Any]] = {}
for service_id, service in SERVICE_ENDPOINT_REGISTRY.items():
    port = int(service["port"])
    entry = PORT_REGISTRY.setdefault(
        port,
        {
            "port": port,
            "services": [],
            "nodes": [],
            "bind_addresses": [],
            "canonical_urls": [],
            "systemd_units": [],
            "health_endpoints": [],
        },
    )
    entry["services"].append(service_id)
    entry["nodes"].append(service["node"])
    entry["bind_addresses"].append(service["bind_address"])
    entry["canonical_urls"].append(service["canonical_url"])
    entry["systemd_units"].append(service["systemd_unit"])
    entry["health_endpoints"].append(service["health_endpoint"])


def canonical_node_id(node_id: Any) -> str:
    raw = str(node_id or "").strip()
    if not raw:
        return ""
    if raw in NODE_ALIAS_MAP:
        return NODE_ALIAS_MAP[raw]
    if raw.startswith("mesh-agent-"):
        return raw
    if raw.startswith("mesh-"):
        base = raw.removeprefix("mesh-")
        return NODE_ALIAS_MAP.get(base, base if base in CANONICAL_NODE_REGISTRY else raw)
    return raw


def node_aliases(canonical_id: str) -> list[str]:
    canonical = canonical_node_id(canonical_id)
    aliases = {canonical}
    aliases.update(alias for alias, target in NODE_ALIAS_MAP.items() if target == canonical)
    if canonical in CANONICAL_NODE_REGISTRY:
        aliases.add(f"mesh-{canonical}")
    return sorted(aliases)


def target_node_matches(target_node: Any, candidate_node: Any) -> bool:
    target = str(target_node or "").strip()
    candidate = str(candidate_node or "").strip()
    if not target or not candidate:
        return False
    return target == candidate or canonical_node_id(target) == canonical_node_id(candidate)


def capability_satisfied(required: Any, capabilities: list[Any] | set[Any] | tuple[Any, ...]) -> bool:
    required_name = str(required or "").strip()
    if not required_name:
        return True
    capability_set = {str(item).strip() for item in capabilities or []}
    if required_name in capability_set:
        return True
    aliases = CAPABILITY_ALIASES.get(required_name, set())
    if aliases.intersection(capability_set):
        return True
    for capability in capability_set:
        if required_name in CAPABILITY_ALIASES.get(capability, set()):
            return True
    return False


def record_classification(node: dict[str, Any]) -> str:
    node_id = str(node.get("node_id") or node.get("id") or "")
    if "canary" in node_id:
        return "canary_record"
    if "smoke" in node_id:
        return "smoke_record"
    if node.get("freshness") == "stale" or node.get("health") == "stale":
        return "stale_record"
    if node_id.startswith("mesh-agent-"):
        return "logical_worker"
    if node_id.startswith("mesh-"):
        return "mesh_alias"
    canonical = canonical_node_id(node_id)
    catalog = CANONICAL_NODE_REGISTRY.get(canonical)
    if catalog:
        return str(catalog.get("record_type") or "physical_server")
    return "unknown"


def decorate_node(node: dict[str, Any]) -> dict[str, Any]:
    decorated = dict(node)
    node_id = str(decorated.get("node_id") or decorated.get("id") or "")
    canonical = canonical_node_id(node_id)
    catalog = CANONICAL_NODE_REGISTRY.get(canonical, {})
    decorated.setdefault("node_id", node_id)
    decorated.setdefault("display_name", catalog.get("display_name") or node_id)
    decorated.setdefault("role", catalog.get("role") or "unknown")
    decorated.setdefault("api_paths", catalog.get("api_paths") or ["fabric_api", "fallback_relay"])
    decorated.setdefault("internal_ips", catalog.get("internal_ips") or [])
    decorated.setdefault("external_ips", catalog.get("external_ips") or [])
    decorated["canonical_node_id"] = canonical
    decorated["record_type"] = record_classification(decorated)
    decorated["aliases"] = node_aliases(canonical) if canonical in CANONICAL_NODE_REGISTRY else [node_id]
    decorated["physical_server"] = canonical in CANONICAL_NODE_REGISTRY and not node_id.startswith("mesh-")
    decorated["logical_worker"] = node_id.startswith("mesh-agent-")
    decorated["safe_to_schedule"] = bool(
        decorated.get("health") == "online"
        and decorated.get("freshness", "fresh") == "fresh"
        and not decorated.get("draining")
    )
    decorated.setdefault("fallback_api_relay", "/v1/fabric/relay")
    decorated.setdefault("management_path", "protected_fabric_api")
    decorated["ssh"] = "emergency_bootstrap_diagnostic_only"
    return decorated


def decorate_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [decorate_node(node) for node in nodes]


def fabric_node_catalog() -> dict[str, dict[str, Any]]:
    return {
        node_id: decorate_node(
            {
                "node_id": node_id,
                "role": data["role"],
                "display_name": data["display_name"],
                "api_paths": data["api_paths"],
                "internal_ips": data.get("internal_ips", []),
                "external_ips": data.get("external_ips", []),
                "source": "registry_catalog",
                "lifecycle": data.get("lifecycle", "active"),
                "network_status_override": data.get("network_status_override"),
                "repair_required": data.get("repair_required"),
                "ssh_access": data.get("ssh_access"),
            }
        )
        for node_id, data in CANONICAL_NODE_REGISTRY.items()
    }


def fleet_summary(nodes: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter()
    canonical_physical: set[str] = set()
    logical_workers: set[str] = set()
    for raw in nodes:
        node = decorate_node(raw)
        counts["records_total"] += 1
        counts[node["record_type"]] += 1
        if node.get("freshness") == "fresh":
            counts["fresh"] += 1
        if node.get("freshness") == "degraded" or node.get("health") == "degraded":
            counts["degraded"] += 1
        if node.get("freshness") == "stale" or node.get("health") == "stale":
            counts["stale"] += 1
        if node.get("health") == "online":
            counts["online"] += 1
        if node["logical_worker"]:
            logical_workers.add(node["node_id"])
            if node.get("health") == "online":
                counts["logical_workers_online"] += 1
        elif node["physical_server"]:
            canonical_physical.add(node["canonical_node_id"])
            if node.get("health") == "online":
                counts["physical_online"] += 1
    counts["physical_servers_total"] = len(canonical_physical)
    counts["logical_workers_total"] = len(logical_workers)
    counts["aliases_total"] = counts["mesh_alias"]
    counts["stale_records"] = max(counts["stale_record"], counts["stale"])
    counts["unknown_records"] = counts["unknown"]
    counts["canary_records"] = counts["canary_record"]
    counts["smoke_records"] = counts["smoke_record"]
    return dict(counts)


def fleet_drift(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    decorated = [decorate_node(node) for node in nodes]
    present_canonical = {
        node["canonical_node_id"]
        for node in decorated
        if node["canonical_node_id"] in CANONICAL_NODE_REGISTRY
        and node.get("source") != "registry_catalog"
    }
    by_canonical: dict[str, list[str]] = defaultdict(list)
    unknown_records: list[str] = []
    stale_reported_online: list[str] = []
    for node in decorated:
        by_canonical[node["canonical_node_id"]].append(node["node_id"])
        if node["canonical_node_id"] not in CANONICAL_NODE_REGISTRY and node["record_type"] != "logical_worker":
            unknown_records.append(node["node_id"])
        if node.get("reported_health") == "online" and node.get("freshness") == "stale":
            stale_reported_online.append(node["node_id"])
    duplicates = {
        canonical: sorted(record_ids)
        for canonical, record_ids in by_canonical.items()
        if len(set(record_ids)) > 1 and canonical in CANONICAL_NODE_REGISTRY
    }
    return {
        "registry_nodes_missing_in_control_plane": sorted(set(CANONICAL_NODE_REGISTRY) - present_canonical),
        "registry_only_records": sorted(
            node["node_id"]
            for node in decorated
            if node["canonical_node_id"] in CANONICAL_NODE_REGISTRY
            and node.get("source") == "registry_catalog"
        ),
        "control_plane_records_not_in_registry": sorted(unknown_records),
        "stale_reported_online": sorted(stale_reported_online),
        "duplicate_canonical_records": duplicates,
    }


def validate_registry() -> list[str]:
    errors: list[str] = []
    for alias, target in sorted(NODE_ALIAS_MAP.items()):
        if target not in CANONICAL_NODE_REGISTRY:
            errors.append(f"alias {alias} points to unknown canonical node {target}")
    for service_id, service in sorted(SERVICE_ENDPOINT_REGISTRY.items()):
        node_id = service.get("node")
        if node_id not in CANONICAL_NODE_REGISTRY:
            errors.append(f"service {service_id} points to unknown node {node_id}")
        port = service.get("port")
        if not isinstance(port, int) or port <= 0 or port > 65535:
            errors.append(f"service {service_id} has invalid port {port!r}")
    return errors
