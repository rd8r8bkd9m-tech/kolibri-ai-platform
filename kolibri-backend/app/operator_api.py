"""Public-portal DTO boundary for protected Home operator data."""

from typing import Any


_TASK_FIELDS = (
    "id",
    "workflow_id",
    "state",
    "priority",
    "owner_agent_id",
    "node_id",
    "budget_limit",
    "attempts",
    "max_retries",
    "created_at",
    "updated_at",
)
_PAGE_FIELDS = ("total", "page", "page_size")
_TASK_TRUTH_FIELDS = (
    "availability",
    "source",
    "as_of",
    "queue_total",
    "total_scope",
)
_CLUSTER_TRUTH_FIELDS = ("availability", "source", "as_of", "task_pages")
_OPERATOR_PATH_PREFIXES = (
    "/api/v1/agents",
    "/api/v1/nodes",
    "/api/v1/providers",
    "/api/v1/tasks",
)
_OPERATOR_EXACT_PATHS = frozenset({
    "/api/v1/cluster/stats",
    "/api/v1/analytics",
})


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def is_operator_api_path(path: str) -> bool:
    return path in _OPERATOR_EXACT_PATHS or any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in _OPERATOR_PATH_PREFIXES
    )


def safe_task_page(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop arbitrary worker result payloads from the portal list response."""

    raw_items = payload.get("items")
    items = raw_items if isinstance(raw_items, list) else []
    result = {field: payload.get(field) for field in _PAGE_FIELDS}
    result["items"] = [
        {field: item.get(field) for field in _TASK_FIELDS}
        for item in items
        if isinstance(item, dict)
    ]
    truth = _dict(payload.get("truth"))
    result["truth"] = {
        field: truth.get(field)
        for field in _TASK_TRUTH_FIELDS
        if field in truth
    }
    return result


def safe_cluster_stats(payload: dict[str, Any]) -> dict[str, Any]:
    """Expose disjoint truth aggregates; topology and membership details stay private."""

    sections = {
        "nodes": (
            "membership_total",
            "connected",
            "fresh",
            "capability_executable",
            "active",
            "verified",
            "blocked",
            "quarantined",
            "stale",
        ),
        "agents": (
            "membership_total", "active", "idle", "paused", "executable", "verified",
        ),
        "tasks": ("total", "running", "queued", "completed", "failed", "cancelled"),
        "resources": ("avg_cpu", "avg_ram", "avg_disk"),
    }
    result = {
        name: {field: _dict(payload.get(name)).get(field) for field in fields}
        for name, fields in sections.items()
    }
    truth = _dict(payload.get("truth"))
    result["truth"] = {
        field: truth.get(field)
        for field in _CLUSTER_TRUTH_FIELDS
        if field in truth
    }
    verification = _dict(truth.get("verification"))
    if verification:
        result["truth"]["verification"] = {
            field: verification.get(field)
            for field in ("availability", "as_of", "status", "reason")
            if field in verification
        }
    return result
