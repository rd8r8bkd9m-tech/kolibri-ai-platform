"""Human-readable Kolibri factory team cards."""

from __future__ import annotations

from typing import Any


ORCHESTRATOR_CARD = {
    "name": "Директор",
    "role": "центральный оркестратор",
    "responsibility": "держит связь с владельцем, знает состояние фабрики, назначает исполнителей и принимает безопасный следующий шаг",
    "home": "удаленный control node",
}


NODE_CARDS = {
    "9fts": {
        "name": "Инженер",
        "role": "implementation lead",
        "responsibility": "выполняет изменения в отдельном worktree и готовит pull request",
    },
    "new": {
        "name": "Ревьюер",
        "role": "independent review",
        "responsibility": "независимо проверяет изменения, риски и тесты",
    },
    "home": {
        "name": "Связной",
        "role": "network gateway",
        "responsibility": "держит сетевой доступ между владельцем, control node и рабочими серверами",
    },
    "main": {
        "name": "Сценарист",
        "role": "staging operator",
        "responsibility": "поднимает безопасные staging-проверки отдельно от production",
    },
    "uiap": {
        "name": "В резерве",
        "role": "quarantined worker",
        "responsibility": "не получает задачи, пока не снят карантин",
    },
    "qjns": {
        "name": "В резерве",
        "role": "quarantined worker",
        "responsibility": "не получает задачи, пока не снят карантин",
    },
}


def node_card(node: dict[str, Any]) -> dict[str, Any]:
    node_id = str(node.get("node_id") or "unknown")
    card = dict(NODE_CARDS.get(node_id, {
        "name": "Исполнитель",
        "role": "worker",
        "responsibility": "получает задачи только по решению директора",
    }))
    card["health"] = node.get("health") or "unknown"
    card["capabilities"] = node.get("capabilities", [])
    card["draining"] = bool(node.get("draining"))
    card["heartbeat_at"] = node.get("heartbeat_at")
    return card
