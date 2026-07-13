"""Canonical Home-first capability and task contracts.

The live factory currently has two different local identities on Home:

* ``home-agent-host`` owns the generic Agent Host lifecycle;
* ``home-codex-provider`` owns the already-authorised owner Codex CLI session.

Treating the latter as a second fleet node would corrupt the 21-node membership
truth.  This module therefore models it as an agent slot of the single logical
``home`` node.  The slot is advertised only after a live Codex login probe and
its capabilities are removed again when the probe fails.

The functions are deliberately side-effect free.  The runtime broker in
``home_factory_orchestrator`` is the only component allowed to publish the
result to the Home Control Plane.
"""

from __future__ import annotations

import uuid
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit


HOME_NODE_ID = "home"
HOME_CODEX_SLOT_ID = "home-codex-provider"
HOME_CODEX_CAPABILITIES = (
    "orchestrator",
    "codex_provider_broker",
    "runner:codex",
)
HOME_CONTROL_PLANE_HOSTS = frozenset({"10.99.0.1", "home"})
LIVE_RUNNER_STATES = frozenset({"available", "healthy", "live", "ready"})


class HomeFactoryContractError(ValueError):
    """A request would violate the single-Home factory contract."""


def validate_home_control_plane_url(value: str | None) -> str:
    """Validate an explicitly configured Home Control Plane URL.

    There is intentionally no default or legacy fallback.  Service discovery
    may populate the environment, but an absent authority is a hard failure.
    """

    raw = str(value or "").strip()
    if not raw:
        raise HomeFactoryContractError("home_control_plane_not_configured")
    parsed = urlsplit(raw)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise HomeFactoryContractError("home_control_plane_url_invalid")
    if hostname not in HOME_CONTROL_PLANE_HOSTS:
        raise HomeFactoryContractError("home_control_plane_authority_required")
    return raw.rstrip("/")


def _unique_strings(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def codex_probe_is_live(probe: Mapping[str, Any]) -> bool:
    tests = probe.get("tests") if isinstance(probe.get("tests"), Mapping) else {}
    login = tests.get("login") if isinstance(tests.get("login"), Mapping) else {}
    binary = tests.get("binary") if isinstance(tests.get("binary"), Mapping) else {}
    cwd = tests.get("cwd") if isinstance(tests.get("cwd"), Mapping) else {}
    return bool(
        str(probe.get("status") or "").lower() in LIVE_RUNNER_STATES
        and str(probe.get("entitlement") or "").lower() == "granted"
        and login.get("ok") is True
        and binary.get("ok") is True
        and cwd.get("ok") is True
    )


def home_broker_heartbeat(
    base_node: Mapping[str, Any],
    codex_probe: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a non-destructive Home node capability-union heartbeat."""

    node_id = str(base_node.get("node_id") or "")
    if node_id != HOME_NODE_ID:
        raise HomeFactoryContractError("home_node_identity_required")

    live = codex_probe_is_live(codex_probe)
    broker_capabilities = set(HOME_CODEX_CAPABILITIES)
    capabilities = [
        capability
        for capability in _unique_strings(base_node.get("capabilities") or [])
        if capability not in broker_capabilities
    ]
    if live:
        capabilities.extend(HOME_CODEX_CAPABILITIES)

    runners = dict(base_node.get("runners") or {})
    runners["codex"] = {
        "status": "available" if live else "blocked",
        "provider": "codex_cli",
        "credential_source": "home_owner_cli_session",
        "secret_exposed": False,
        "checked_at": codex_probe.get("checked_at"),
        "model": codex_probe.get("model") or "account-default",
        "error_type": None if live else codex_probe.get("error_code") or "runner_auth_blocked",
    }

    slots = dict(base_node.get("agent_slots") or {})
    slots[HOME_CODEX_SLOT_ID] = {
        "slot_id": HOME_CODEX_SLOT_ID,
        "node_id": HOME_NODE_ID,
        "status": "live" if live else "blocked",
        "capabilities": list(HOME_CODEX_CAPABILITIES) if live else [],
        "runner": "codex",
        "checked_at": codex_probe.get("checked_at"),
        "secret_exposed": False,
    }

    # Do not send ``agent_id``: the generic Home Agent Host remains the node's
    # primary process identity.  Lease ownership identifies this broker slot.
    return {
        "node_id": HOME_NODE_ID,
        "capabilities": capabilities,
        "runners": runners,
        "agent_slots": slots,
        "provider_broker_status": "live" if live else "blocked",
    }


def home_codex_route_readiness(node: Mapping[str, Any]) -> dict[str, Any]:
    """Return a precise readiness verdict for the Home Codex broker route."""

    missing: list[str] = []
    if str(node.get("node_id") or "") != HOME_NODE_ID:
        missing.append("home_node_identity")
    if str(node.get("health") or "").lower() not in {"online", "healthy", "ready"}:
        missing.append("home_node_health")
    if str(node.get("freshness") or "fresh").lower() != "fresh":
        missing.append("home_node_freshness")
    if node.get("draining") is True:
        missing.append("home_node_not_draining")
    if node.get("schedulable") is False:
        missing.append("home_node_schedulable")

    capabilities = set(_unique_strings(node.get("capabilities") or []))
    for capability in HOME_CODEX_CAPABILITIES:
        if capability not in capabilities:
            missing.append(capability)

    runners = node.get("runners") if isinstance(node.get("runners"), Mapping) else {}
    codex = runners.get("codex") if isinstance(runners.get("codex"), Mapping) else {}
    if str(codex.get("status") or "").lower() not in LIVE_RUNNER_STATES:
        missing.append("codex_runner_live")

    slots = node.get("agent_slots") if isinstance(node.get("agent_slots"), Mapping) else {}
    slot = slots.get(HOME_CODEX_SLOT_ID) if isinstance(slots.get(HOME_CODEX_SLOT_ID), Mapping) else {}
    if str(slot.get("status") or "").lower() != "live":
        missing.append("home_codex_slot_live")

    return {
        "ready": not missing,
        "authority": HOME_NODE_ID,
        "slot_id": HOME_CODEX_SLOT_ID,
        "required_capabilities": list(HOME_CODEX_CAPABILITIES),
        "missing": missing,
    }


def build_home_codex_task(
    objective: str,
    *,
    task_id: str | None = None,
    idempotency_key: str | None = None,
    max_attempts: int = 2,
) -> dict[str, Any]:
    """Build the compatibility envelope for one bounded Home Codex task."""

    objective = str(objective or "").strip()
    if not objective:
        raise HomeFactoryContractError("objective_required")
    if not 1 <= max_attempts <= 5:
        raise HomeFactoryContractError("max_attempts_out_of_range")
    task_id = task_id or f"KOL-HOME-CODEX-{uuid.uuid4().hex[:12]}"
    return {
        "task_id": task_id,
        "idempotency_key": idempotency_key or f"home-codex:{task_id}",
        "kind": "owner_remote_task",
        "objective": objective,
        "source": "home_program_controller",
        "command_node": HOME_NODE_ID,
        "target_node": HOME_NODE_ID,
        "required_capability": "codex_provider_broker",
        "required_capabilities": list(HOME_CODEX_CAPABILITIES),
        "runner": "codex",
        "public_model": "kolibri",
        "read_only": True,
        "no_push": True,
        "product_code_modification_forbidden": True,
        "write_scope": [],
        "max_attempts": max_attempts,
        # Compatibility with the current Python Control Plane, which counts
        # retries after the first attempt.  Rust authority will use only
        # ``max_attempts`` after its parity gate.
        "max_retries": max_attempts - 1,
        "artifact_policy": {
            "required": True,
            "content_addressed": True,
            "bind_attempt_id": True,
            "require_sha256": True,
        },
        "verifier_policy": {
            "required": True,
            "independent_identity": True,
            "terminal_without_verdict": False,
        },
        "approval_policy": {"class": "read_only", "required": False},
    }
