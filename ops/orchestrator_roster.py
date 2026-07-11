"""Human-readable Kolibri factory team cards."""

from __future__ import annotations

from typing import Any


ORCHESTRATOR_CARD = {
    "name": "Директор",
    "role": "центральный оркестратор",
    "responsibility": "держит связь с владельцем, знает состояние фабрики, назначает исполнителей и принимает безопасный следующий шаг",
    "home": "Home-only Control Plane",
}


ROLE_CARDS = (
    (
        frozenset({"review", "independent_review"}),
        {
            "name": "Ревьюер",
            "role": "independent review",
            "responsibility": "независимо проверяет изменения, риски и тесты",
        },
    ),
    (
        frozenset({"implementation", "generic_implementation"}),
        {
            "name": "Инженер",
            "role": "implementation worker",
            "responsibility": "выполняет изменения в отдельном worktree и возвращает проверенный результат",
        },
    ),
    (
        frozenset({"orchestrator", "control_plane"}),
        {
            "name": "Координатор",
            "role": "orchestration worker",
            "responsibility": "координирует разрешённые задачи и следит за их состоянием",
        },
    ),
    (
        frozenset({"network_gateway", "mesh_registrar"}),
        {
            "name": "Связной",
            "role": "network gateway",
            "responsibility": "поддерживает динамическую mesh-связность и регистрацию узлов",
        },
    ),
)

DEFAULT_CARD = {
    "name": "Исполнитель",
    "role": "worker",
    "responsibility": "получает только совместимые задачи из Home Control Plane",
}


def node_card(node: dict[str, Any]) -> dict[str, Any]:
    node_id = str(node.get("node_id") or "unknown")
    capabilities = {str(value) for value in node.get("capabilities", [])}
    labels = node.get("labels") if isinstance(node.get("labels"), dict) else {}
    if node.get("draining") or node.get("quarantined") or labels.get("quarantined") is True:
        card = {
            "name": "В резерве",
            "role": "quarantined worker",
            "responsibility": "не получает задачи, пока не снят карантин",
        }
    else:
        card = dict(DEFAULT_CARD)
        for required, candidate in ROLE_CARDS:
            if capabilities.intersection(required):
                card = dict(candidate)
                break
    # Enrollment labels may customize presentation, but physical node names
    # never select a role. This keeps every new mesh member dynamic.
    for field in ("name", "role", "responsibility"):
        label = labels.get(f"display_{field}")
        if isinstance(label, str) and label.strip():
            card[field] = label.strip()[:500]
    card["node_id"] = node_id
    card["health"] = node.get("health") or "unknown"
    card["freshness"] = node.get("freshness")
    card["heartbeat_age_seconds"] = node.get("heartbeat_age_seconds")
    card["capabilities"] = sorted(capabilities)
    card["draining"] = bool(node.get("draining"))
    card["heartbeat_at"] = node.get("heartbeat_at")
    return card
