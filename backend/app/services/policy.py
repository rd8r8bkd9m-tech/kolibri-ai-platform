
from __future__ import annotations
from typing import Any
from .state import STORE


def resolve_role(role_id: str) -> dict[str, Any]:
    return STORE.manifest["roles"].get(role_id) or STORE.manifest["roles"]["client"]


def has_capability(role: dict[str, Any], capability: str) -> bool:
    grants = role.get("grants", [])
    return "*" in grants or capability in grants


def resolve_intent(text: str, role_id: str = "client") -> dict[str, Any]:
    value = (text or "").lower()
    intents = sorted(STORE.manifest["intents"].values(), key=lambda item: int(item.get("priority", 0)), reverse=True)
    for intent in intents:
        if any(str(trigger).lower() in value for trigger in intent.get("triggers", [])):
            return intent
    role = resolve_role(role_id)
    return STORE.manifest["intents"].get(role.get("default_intent")) or STORE.manifest["intents"]["estimate_start"]


def resolve_os_turn(role_id: str, text: str, device_id: str = "auto") -> dict[str, Any]:
    role = resolve_role(role_id)
    plan = STORE.manifest["plans"].get(role["plan"], {"id": role["plan"], "label": role["plan"]})
    device = STORE.manifest["devices"].get(device_id, STORE.manifest["devices"]["auto"])
    intent = resolve_intent(text, role["id"])
    allowed = []
    hidden = []
    denied_capabilities: list[str] = []
    for component in STORE.manifest["components"].values():
        if intent["id"] not in component.get("intents", []) and "*" not in component.get("intents", []):
            continue
        missing = [cap for cap in component.get("required", []) if not has_capability(role, cap)]
        if missing:
            hidden.append(component)
            denied_capabilities.extend(missing)
        else:
            allowed.append(component)
    denied = []
    for cap in sorted(set(denied_capabilities)):
        denied.append({"id": cap, **STORE.manifest.get("capabilities", {}).get(cap, {})})
    assistant = intent.get("assistant", "Открываю доступные окна.")
    if hidden and not allowed:
        assistant = "Эта функция недоступна для вашей роли или тарифа. Я не отрисовал закрытые окна."
    return {"role": role, "plan": plan, "device": device, "intent": intent, "components": allowed, "hidden": hidden, "denied_capabilities": denied, "assistant": assistant}


def can_render_component(role_id: str, component_id: str) -> bool:
    role = resolve_role(role_id)
    component = STORE.manifest.get("components", {}).get(component_id)
    if not component:
        return False
    return all(has_capability(role, capability) for capability in component.get("required", []))
