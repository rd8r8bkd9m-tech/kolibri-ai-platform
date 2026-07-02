"""MIMO/subagent pool policy shared by bootstrap, runtime and status views."""

from __future__ import annotations

import os
from typing import Any

DEFAULT_MAX_AGENTS_PER_SERVER = 20
DEFAULT_AGENT_CPU_QUOTA_PERCENT = 400
DEFAULT_AGENT_MEMORY_MAX = "2G"
DEFAULT_AGENT_TASKS_MAX = 256
DEFAULT_AGENT_NOFILE = 8192


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def max_agents_per_server(env: dict[str, str] | None = None) -> int:
    source = env or os.environ
    return _positive_int(source.get("KOLIBRI_MIMO_MAX_AGENTS_PER_SERVER"), DEFAULT_MAX_AGENTS_PER_SERVER)


def clamp_agent_capacity(requested: Any, env: dict[str, str] | None = None) -> int:
    cap = max_agents_per_server(env)
    requested_count = _positive_int(requested, cap)
    return min(requested_count, cap)


def pool_policy(env: dict[str, str] | None = None) -> dict[str, Any]:
    source = env or os.environ
    max_agents = max_agents_per_server(source)
    return {
        "policy_id": "kolibri-mimo-pool-per-server-v1",
        "max_agents_per_server": max_agents,
        "default_agent_max_inflight": clamp_agent_capacity(source.get("KOLIBRI_MAX_INFLIGHT", "1"), source),
        "resource_caps": {
            "cpu_quota_percent": _positive_int(
                source.get("KOLIBRI_AGENT_CPU_QUOTA_PERCENT"),
                DEFAULT_AGENT_CPU_QUOTA_PERCENT,
            ),
            "memory_max": source.get("KOLIBRI_AGENT_MEMORY_MAX", DEFAULT_AGENT_MEMORY_MAX),
            "tasks_max": _positive_int(source.get("KOLIBRI_AGENT_TASKS_MAX"), DEFAULT_AGENT_TASKS_MAX),
            "nofile": _positive_int(source.get("KOLIBRI_AGENT_NOFILE"), DEFAULT_AGENT_NOFILE),
        },
        "scheduler_contract": {
            "logical_agents_are_not_os_processes": True,
            "requires_fresh_heartbeat": True,
            "requires_runner_auth_classified": True,
            "requires_resource_probe": True,
            "stale_nodes_count_as_capacity": False,
        },
        "external_api_guardrails": {
            "no_provider_bypass": True,
            "no_fake_accounts": True,
            "respect_provider_terms_and_rate_limits": True,
            "secrets_never_returned_in_status": True,
        },
    }


def node_pool_status(node: dict[str, Any], env: dict[str, str] | None = None) -> dict[str, Any]:
    policy = pool_policy(env)
    configured = clamp_agent_capacity(
        node.get("max_inflight")
        or node.get("agent_pool", {}).get("configured_agents")
        or policy["default_agent_max_inflight"],
        env,
    )
    freshness = node.get("freshness")
    health = node.get("health")
    ready = freshness in {None, "fresh"} and health in {None, "online"}
    active = 1 if node.get("active_task") else 0
    return {
        "policy_id": policy["policy_id"],
        "configured_agents": configured,
        "max_agents_per_server": policy["max_agents_per_server"],
        "available_agents": max(0, configured - active) if ready else 0,
        "active_agents": active,
        "ready": ready,
        "blocked_reason": "" if ready else "node_not_fresh_or_online",
        "resource_caps": policy["resource_caps"],
        "external_api_guardrails": policy["external_api_guardrails"],
    }
