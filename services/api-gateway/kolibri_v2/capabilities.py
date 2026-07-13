from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Capability:
    id: str
    label: str
    route: bool
    executor: bool
    renderer: bool
    evidence: bool
    roles: tuple[str, ...]

    @property
    def available(self) -> bool:
        return self.route and self.executor and self.renderer and self.evidence


class CapabilityRegistry:
    def __init__(self):
        self._items = [
            Capability("chat", "Диалог", True, True, True, True, ("client","operator","owner","developer")),
            Capability("history", "Проекты и история", True, True, True, True, ("client","operator","owner","developer")),
            Capability("estimates", "Сметы", True, True, True, True, ("client","operator","owner")),
            Capability("documents", "Документы", True, True, True, True, ("client","operator","owner")),
            Capability("files", "Файлы", True, True, True, True, ("client","operator","owner","developer")),
            Capability("factory", "Фабрика", True, True, False, True, ("operator","owner")),
            Capability("images", "Изображения", False, False, False, False, ("client","operator","owner")),
            Capability("sites", "Сайты и приложения", False, False, False, False, ("client","operator","owner","developer")),
            Capability("code", "Код", False, False, False, False, ("developer","owner")),
        ]

    def for_role(self, role: str) -> list[dict[str, Any]]:
        return [self.serialize(item) for item in self._items if role in item.roles and item.available]

    def all(self) -> list[dict[str, Any]]:
        return [self.serialize(item) for item in self._items]

    @staticmethod
    def serialize(item: Capability) -> dict[str, Any]:
        return {
            "id": item.id,
            "label": item.label,
            "available": item.available,
            "evidence_gate": {
                "route": item.route,
                "executor": item.executor,
                "renderer": item.renderer,
                "evidence": item.evidence,
            },
        }
