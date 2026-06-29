from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EndpointContract:
    method: str
    path: str
    purpose: str
    owner_action: bool = True
    requires_confirmation: bool = False
    cacheable: bool = False


OWNER_CONTROL_PLANE_ENDPOINTS: tuple[EndpointContract, ...] = (
    EndpointContract("GET", "/health", "Control Plane health", cacheable=True),
    EndpointContract("GET", "/v1/health", "Control Plane v1 health", cacheable=True),
    EndpointContract("GET", "/v1/nodes", "Node inventory, heartbeat, drain and capacity", cacheable=True),
    EndpointContract("POST", "/v1/nodes/<node_id>/drain", "Drain or undrain a node", requires_confirmation=True),
    EndpointContract("GET", "/v1/tasks?summary=1&compact=1", "Compact task and queue summary", cacheable=True),
    EndpointContract("GET", "/v1/tasks?state=<state>&limit=<n>", "Filtered task list", cacheable=True),
    EndpointContract("GET", "/v1/tasks/<task_id>", "Task detail and lifecycle", cacheable=True),
    EndpointContract("POST", "/v1/tasks", "Submit a validated task envelope", requires_confirmation=True),
    EndpointContract("POST", "/v1/tasks/<task_id>/cancel", "Cancel a task", requires_confirmation=True),
    EndpointContract("POST", "/v1/tasks/<task_id>/annotate", "Annotate task result or operator note"),
    EndpointContract("GET", "/v1/agent-messages?target=all&limit=<n>", "Owner-visible agent feed", cacheable=True),
    EndpointContract("POST", "/v1/agent-messages", "Publish an operator/status message"),
)

WORKER_ONLY_ENDPOINTS: tuple[EndpointContract, ...] = (
    EndpointContract("POST", "/v1/tasks/lease", "Worker lease acquisition", owner_action=False),
    EndpointContract("POST", "/v1/tasks/<task_id>/heartbeat", "Worker task heartbeat", owner_action=False),
    EndpointContract("POST", "/v1/tasks/<task_id>/complete", "Worker task completion", owner_action=False),
    EndpointContract("POST", "/v1/tasks/<task_id>/fail", "Worker task failure", owner_action=False),
    EndpointContract("POST", "/v1/nodes/register", "Worker node registration", owner_action=False),
    EndpointContract("POST", "/v1/nodes/<node_id>/heartbeat", "Worker node heartbeat", owner_action=False),
)

ROADMAP_ENDPOINTS: tuple[EndpointContract, ...] = (
    EndpointContract("GET", "/v1/filesystem", "Namespace and manifest metadata", cacheable=True),
    EndpointContract("GET", "/v1/tasks/<task_id>/artifacts", "Safe artifact manifest", cacheable=True),
    EndpointContract("POST", "/v1/tasks/<task_id>/requeue", "Explicit owner requeue", requires_confirmation=True),
    EndpointContract("GET", "/v1/events", "Live event stream", cacheable=False),
)

DESKTOP_FACADE_PLACEHOLDERS: tuple[EndpointContract, ...] = (
    EndpointContract("GET", "/api/desktop-control/health", "Backend facade for health", cacheable=True),
    EndpointContract("GET", "/api/desktop-control/nodes", "Backend facade for nodes", cacheable=True),
    EndpointContract("GET", "/api/desktop-control/tasks", "Backend facade for task summary/list", cacheable=True),
    EndpointContract("GET", "/api/desktop-control/tasks/<task_id>", "Backend facade for task detail", cacheable=True),
    EndpointContract("POST", "/api/desktop-control/tasks", "Backend facade for envelope submit", requires_confirmation=True),
    EndpointContract("POST", "/api/desktop-control/tasks/<task_id>/cancel", "Backend facade for cancel", requires_confirmation=True),
    EndpointContract("POST", "/api/desktop-control/tasks/<task_id>/annotate", "Backend facade for annotation"),
    EndpointContract("POST", "/api/desktop-control/nodes/<node_id>/drain", "Backend facade for drain/undrain", requires_confirmation=True),
    EndpointContract("GET", "/api/desktop-control/agent-messages", "Backend facade for agent feed", cacheable=True),
    EndpointContract("POST", "/api/desktop-control/agent-messages", "Backend facade for operator message"),
)

REQUIRED_ENVELOPE_FIELDS: tuple[str, ...] = ("task_id", "kind", "goal", "acceptance", "source")
DANGEROUS_PERMISSION_PACKS: tuple[str, ...] = ("full_autonomy", "shell", "admin", "root")
PROJECT_SYNC_PENDING = "Project sync: pending"

SECRET_MARKERS: tuple[str, ...] = (
    ".env",
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "cookies.sqlite",
    "auth.json",
    "id_rsa",
    "id_ed25519",
)

TOKEN_RE = re.compile(
    r"(?i)\b("
    r"api[_-]?key|authorization|bearer|cookie|github[_-]?token|ghp_[a-z0-9_]+|"
    r"token|secret|password"
    r")\b\s*[:=]\s*['\"]?[^'\"\s]+"
)
LOCAL_PATH_RE = re.compile(
    r"(?<![\w.-])(?:/Users|/home|/tmp|/var/folders|/opt/kolibri-ai|/root)/[^\s,;)]*"
)


def endpoint_pairs(endpoints: tuple[EndpointContract, ...]) -> set[tuple[str, str]]:
    return {(endpoint.method, endpoint.path) for endpoint in endpoints}


def validate_desktop_envelope(envelope: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_ENVELOPE_FIELDS:
        value = envelope.get(field)
        if value in (None, "", []):
            errors.append(f"missing required field: {field}")

    acceptance = envelope.get("acceptance")
    if acceptance is not None and not isinstance(acceptance, list):
        errors.append("acceptance must be a list")

    source = envelope.get("source")
    if source is not None and not isinstance(source, dict):
        errors.append("source must be an object")

    payload = str(envelope)
    for marker in SECRET_MARKERS:
        if marker in payload:
            errors.append(f"secret marker is not allowed in envelope: {marker}")

    return errors


def permission_pack_warnings(envelope: dict[str, Any]) -> list[str]:
    pack = str(envelope.get("permission_pack") or "")
    if pack in DANGEROUS_PERMISSION_PACKS:
        return [f"permission_pack={pack} requires explicit owner confirmation"]
    return []


def sanitize_owner_summary(text: str) -> str:
    redacted = TOKEN_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    redacted = LOCAL_PATH_RE.sub("[LOCAL_PATH_REDACTED]", redacted)
    for marker in SECRET_MARKERS:
        redacted = redacted.replace(marker, "[SECRET_MARKER_REDACTED]")
    return redacted
