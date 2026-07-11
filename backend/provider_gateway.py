"""Real provider gateway for the single public Kolibri model.

Provider names, runner models and failure provenance stay under ``technical``.
The gateway never returns a synthetic assistant answer: success requires a
zero exit status, non-empty parsed assistant output and hashed evidence.
"""

from __future__ import annotations

import hashlib
import importlib.util
import ipaddress
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit

from data_paths import DATA_DIR


PUBLIC_MODEL = "kolibri"
PUBLIC_IDENTITY_CONTRACT_VERSION = "kolibri.public-identity.v1"
PUBLIC_IDENTITY_INSTRUCTION = (
    "Execution identity contract: this is a system-level public identity boundary. "
    "You are Kolibri, the public AI assistant. If the customer asks who you are, "
    "identify only as Kolibri. Never claim, reveal, or imply an internal provider, "
    "runner, model, vendor, or agent identity; those details belong only in technical "
    "evidence and the owner Control surface. Do not invent capabilities. Follow the "
    "requested response format exactly, including JSON-only contracts."
)
DEFAULT_PROVIDER_ORDER = ("factory", "mimo", "codex", "deepseek", "local")
SUPPORTED_PROVIDERS = frozenset(DEFAULT_PROVIDER_ORDER)
DEFAULT_CODEX_MODELS = (
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.3-codex-spark",
)
SAFE_RUNNER_ENV_KEYS = {
    "CODEX_HOME", "HOME", "LANG", "LC_ALL", "LOGNAME", "MIMO_HOME",
    "NO_PROXY", "PATH", "SSL_CERT_DIR", "SSL_CERT_FILE", "TERM", "TMPDIR",
    "USER", "XDG_CACHE_HOME", "XDG_CONFIG_HOME",
}
SAFE_RESULT_KEYS = ("answer", "response", "result", "output", "summary")
TOOL_EVENT_MARKERS = (
    "tool", "command_execution", "command.exec", "mcp", "web_search",
    "computer", "browser", "file_change", "image_generation",
)
SUCCESS_STATES = frozenset({"completed", "complete", "succeeded", "success", "ok"})
FAILURE_STATES = frozenset({"failed", "failure", "error", "cancelled", "canceled", "blocked"})
ARTIFACT_KEYS = frozenset({
    "artifact", "artifacts", "artifact_ref", "artifact_refs", "attachment",
    "attachments", "file_path", "output_file", "output_files", "uri", "url",
})
MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,119}$")
LOCAL_MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/#:-]{0,159}$")
DEEPSEEK_API_HOST = "api.deepseek.com"
FACTORY_SUPPORTED_RUNNERS = frozenset({"mimo", "codex"})
FACTORY_RUNNER_CONTRACT = "kolibri.factory-provider.readonly.v1"
FACTORY_TERMINAL_STATES = frozenset({
    "blocked", "cancelled", "canceled", "completed", "dead", "dead_letter", "failed",
})
_INTERNAL_EXECUTOR_LABEL = (
    r"(?:mimo(?:\s+code(?:\s+agent)?)?|codex|chatgpt|"
    r"gpt(?:[-\s]?\d+(?:\.\d+)*)?|openai(?:\s+(?:assistant|agent|model))?|"
    r"deepseek(?:\s+(?:assistant|agent|model))?|qwen(?:[-\w.]*)?)"
)
_INTERNAL_IDENTITY_CLAIM_PATTERNS = (
    re.compile(
        rf"(?:\bя\b\s*(?:(?:[-—:]|являюсь|это)\s*)?"
        rf"|\bменя\s+(?:зовут|называют)\s+"
        rf"|\bi\s+am\s+(?:(?:the|an?)\s+)?"
        rf"|\bi['’]m\s+(?:(?:the|an?)\s+)?"
        rf"|\bmy\s+(?:name|provider|runner|model|executor)\s+is\s+"
        rf"|\bas\s+(?:(?:the|an?)\s+)(?:internal\s+)?)"
        rf"(?:внутренн(?:ий|яя|ее)\s+|internal\s+)?\b{_INTERNAL_EXECUTOR_LABEL}\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?:\bмой\s+(?:провайдер|исполнитель|раннер|модель)\b"
        rf"|\bmy\s+(?:provider|runner|model|executor)\b)"
        rf"[^.\n!?]{{0,60}}\b{_INTERNAL_EXECUTOR_LABEL}\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?:\bя\s+(?:работаю|запущен|запущена|отвечаю)\s+(?:через|на)\s+"
        rf"|\bi\s+(?:run|operate)\s+on\s+|\bi\s+am\s+powered\s+by\s+)"
        rf"\b{_INTERNAL_EXECUTOR_LABEL}\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:mimo\s+code\s+agent|"
        r"(?:codex|chatgpt|openai|deepseek|qwen(?:[-\w.]*))\s+"
        r"(?:агент|ассистент|модель|agent|assistant|model))"
        rf"\s*[.!]?\s*$",
        re.IGNORECASE,
    ),
)


def _load_home_endpoint_resolver():
    endpoint_path = Path(__file__).resolve().parents[1] / "ops" / "control_plane_endpoint.py"
    spec = importlib.util.spec_from_file_location("kolibri_provider_home_endpoint", endpoint_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("canonical_home_control_plane_resolver_missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.resolve_home_control_plane_url


resolve_home_control_plane_url = _load_home_endpoint_resolver()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text") or "")
    if isinstance(content, list):
        return "".join(_content_text(item) for item in content)
    return ""


def public_identity_contract_violation(text: str) -> bool:
    """Return whether an answer claims a hidden executor as its public identity.

    Provider names may legitimately appear in customer content (for example, a
    comparison requested by the customer), so the guard is deliberately scoped
    to first-person/self-description claims.  It never rewrites provider output:
    a violating attempt fails and normal provider fallback may continue.
    """

    normalized = " ".join(str(text or "").split())
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in _INTERNAL_IDENTITY_CLAIM_PATTERNS)


def extract_assistant_text(stdout: str) -> str:
    final_messages: list[str] = []
    text_parts: list[str] = []
    deltas: list[str] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "")
        lowered_type = event_type.lower()
        if event_type in {"error", "turn.failed"}:
            continue
        part = event.get("part")
        if (
            isinstance(part, dict) and part.get("type") == "text" and part.get("text")
            and not any(marker in lowered_type for marker in TOOL_EVENT_MARKERS)
        ):
            text_parts.append(str(part["text"]))
        message = event.get("msg")
        if isinstance(message, dict):
            message_type = str(message.get("type") or "").lower()
            text = message.get("message") or message.get("text") or _content_text(message.get("content"))
            assistant_message = any(marker in message_type for marker in ("assistant", "agent_message", "text_delta"))
            if text and assistant_message and not any(marker in message_type for marker in TOOL_EVENT_MARKERS):
                (deltas if "delta" in message_type else final_messages).append(str(text))
        text = event.get("message") or event.get("text") or _content_text(event.get("content"))
        if text:
            if "delta" in event_type:
                deltas.append(str(text))
            elif event_type in {"agent_message", "assistant_message", "message"}:
                final_messages.append(str(text))
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") in {"message", "assistant_message", "agent_message"}:
            text = item.get("message") or item.get("text") or _content_text(item.get("content"))
            role = str(item.get("role") or "assistant").lower()
            if text and role in {"assistant", "agent"}:
                final_messages.append(str(text))
        # Mimo may emit a top-level final result.  Do not mistake command/tool
        # output for assistant output merely because it uses an ``output`` key.
        is_tool_event = any(marker in lowered_type for marker in TOOL_EVENT_MARKERS)
        is_final_result = lowered_type in {
            "", "result", "final", "response.completed", "turn.completed",
            "assistant.completed", "message.completed",
        }
        if is_final_result and not is_tool_event:
            for key in SAFE_RESULT_KEYS:
                value = event.get(key)
                text = value if isinstance(value, str) else _content_text(value)
                if text:
                    final_messages.append(str(text))
    for values in (final_messages, text_parts, deltas):
        result = "".join(values).strip()
        if result:
            return result
    # Canonical runners are invoked in JSON mode. Plain stdout is log output,
    # not proof of an assistant response.
    return ""


def structured_error_type(stdout: str) -> str | None:
    """Classify JSONL error events without copying provider error bodies."""
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "")
        # Codex can emit recoverable item-level diagnostics before a valid
        # assistant message and terminal ``turn.completed``. Only terminal or
        # top-level provider errors invalidate the whole attempt.
        if event_type not in {"error", "turn.failed"}:
            continue
        serialized = json.dumps(event, ensure_ascii=False).lower()
        if (
            "risk_control" in serialized
            or "risk control" in serialized
            or re.search(r'"(?:code|statuscode)"\s*:\s*"?441"?', serialized)
        ):
            return "provider_risk_control"
        if "requires a newer version" in serialized or "upgrade" in serialized:
            return "provider_runner_outdated"
        if "usage limit" in serialized or "rate limit" in serialized or "quota" in serialized:
            return "provider_usage_limit"
        if any(marker in serialized for marker in (
            "model not found", "model is not available", "model unavailable",
            "unsupported model", "not enabled for this account", "not provisioned",
        )):
            return "provider_model_unavailable"
        if "unauthorized" in serialized or '"status":401' in serialized:
            return "provider_auth_failed"
        if "forbidden" in serialized or '"status":403' in serialized:
            return "provider_access_denied"
        return "provider_runtime_failed"
    return None


def classify_failure(stderr: str, returncode: int | None) -> str:
    lowered = stderr.lower()
    if (
        "risk_control" in lowered
        or "risk control" in lowered
        or re.search(r'"?(?:code|statuscode)"?\s*[:=]\s*"?441"?', lowered)
    ):
        return "provider_risk_control"
    if "usage limit" in lowered or "rate limit" in lowered or "quota" in lowered:
        return "provider_usage_limit"
    if any(marker in lowered for marker in (
        "model not found", "model is not available", "model unavailable",
        "unsupported model", "not enabled for this account", "not provisioned",
    )):
        return "provider_model_unavailable"
    if "401" in lowered or "unauthorized" in lowered or "authentication" in lowered:
        return "provider_auth_failed"
    if "403" in lowered or "forbidden" in lowered or "illegal_access" in lowered:
        return "provider_access_denied"
    if returncode is None:
        return "provider_timeout"
    if returncode == 127:
        return "provider_runner_missing"
    return "provider_runtime_failed"


def route_capability_probe(error_type: str | None = None, *, succeeded: bool = False) -> dict[str, str]:
    if succeeded:
        return {"status": "available", "reason": "verified_execution"}
    if error_type in {
        "factory_control_endpoint_invalid", "factory_no_fresh_capable_worker",
        "provider_runner_missing", "provider_model_unavailable",
        "provider_model_configuration_invalid", "provider_runner_outdated",
    }:
        return {"status": "unavailable", "reason": str(error_type)}
    return {"status": "degraded", "reason": str(error_type or "execution_not_verified")}


def safe_runner_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    """Build an allowlisted subprocess environment without service secrets."""
    current = source if source is not None else os.environ
    environment = {
        key: str(current[key])
        for key in sorted(SAFE_RUNNER_ENV_KEYS)
        if key in current and current[key]
    }
    environment.setdefault("LANG", "C.UTF-8")
    environment.setdefault("PATH", os.defpath)
    return environment


def _stable_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def _safe_token(value: Any, fallback: str = "unknown") -> str:
    text = str(value or "").strip().lower()
    if re.search(r"(?:sk|ghp|github_pat|xox[baprs])[-_][a-z0-9_-]{10,}", text, re.IGNORECASE):
        return fallback
    if re.search(r"bearer\s+[a-z0-9._~+/=-]{10,}", text, re.IGNORECASE):
        return fallback
    text = re.sub(r"[^a-z0-9_.:-]+", "-", text).strip("-:.")
    return (text or fallback)[:160]


def _tool_name(node: dict[str, Any], combined_type: str) -> str:
    for key in ("tool_name", "tool", "name", "capability_id"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return _safe_token(value)
    server = node.get("server") or node.get("server_name")
    method = node.get("method") or node.get("operation")
    if server and method:
        return _safe_token(f"{server}.{method}")
    lowered = combined_type.lower()
    if "command" in lowered:
        return "shell"
    if "web_search" in lowered:
        return "web_search"
    if "file_change" in lowered:
        return "filesystem"
    if "browser" in lowered:
        return "browser"
    if "computer" in lowered:
        return "computer_use"
    if "image_generation" in lowered:
        return "image_generation"
    return _safe_token(combined_type, "tool")


def _tool_status(node: dict[str, Any], container_type: str) -> str:
    explicit = _safe_token(node.get("status") or "", "")
    if explicit in FAILURE_STATES or node.get("error"):
        return "failed"
    if explicit in SUCCESS_STATES:
        return "succeeded"
    lowered = container_type.lower()
    if "failed" in lowered or "error" in lowered:
        return "failed"
    if any(marker in lowered for marker in ("completed", "result", "succeeded")):
        return "succeeded"
    return "running"


def _artifact_ref(value: Any, _work_dir: Path) -> dict[str, Any] | None:
    declared_sha: str | None = None
    declared_size: int | None = None
    if isinstance(value, dict):
        raw_reference = next((
            value.get(key) for key in ("uri", "url", "path", "file_path", "name")
            if isinstance(value.get(key), str) and value.get(key)
        ), None)
        candidate_sha = value.get("sha256")
        if isinstance(candidate_sha, str) and re.fullmatch(r"[a-fA-F0-9]{64}", candidate_sha):
            declared_sha = candidate_sha.lower()
        if isinstance(value.get("size_bytes"), int) and value["size_bytes"] >= 0:
            declared_size = value["size_bytes"]
    elif isinstance(value, str):
        raw_reference = value
    else:
        return None
    if not raw_reference:
        return None
    raw_reference = str(raw_reference)
    digest = hashlib.sha256(raw_reference.encode("utf-8", errors="replace")).hexdigest()
    parsed = urlsplit(raw_reference)
    reference: dict[str, Any] = {"reference_sha256": digest}
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        reference["kind"] = "web"
        reference["origin"] = f"{parsed.scheme}://{parsed.hostname}"
        name = Path(parsed.path).name
    else:
        reference["kind"] = "file"
        raw_path = Path(raw_reference).expanduser()
        name = raw_path.name
    safe_name = _safe_token(name or "artifact", "artifact")[:180]
    reference["name"] = safe_name or "artifact"
    if reference["kind"] == "file":
        # Do not retain raw filesystem paths. The digest plus safe basename is
        # a stable artifact reference without leaking directory/user data.
        reference["locator"] = f"artifact://{digest[:16]}/{reference['name']}"
    if declared_sha:
        reference["content_sha256"] = declared_sha
    if declared_size is not None:
        reference["size_bytes"] = declared_size
    return reference


def _collect_artifacts(value: Any, work_dir: Path, *, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 5:
        return []
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        node_type = str(value.get("type") or "").lower()
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in ARTIFACT_KEYS or "artifact" in normalized:
                values = child if isinstance(child, list) else [child]
                for item in values:
                    reference = _artifact_ref(item, work_dir)
                    if reference:
                        found.append(reference)
            elif "artifact" in node_type or "file_change" in node_type:
                if normalized in {"path", "file", "name"}:
                    reference = _artifact_ref(child, work_dir)
                    if reference:
                        found.append(reference)
            if isinstance(child, (dict, list)):
                found.extend(_collect_artifacts(child, work_dir, depth=depth + 1))
    elif isinstance(value, list):
        for child in value:
            found.extend(_collect_artifacts(child, work_dir, depth=depth + 1))
    return found


def extract_tool_provenance(stdout: str, provider: str, work_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract hashes and safe identifiers from JSONL tool events.

    Raw arguments, command text, results, and provider error bodies are never
    retained.  Started/completed events with the same call id are folded into
    one provenance record.
    """
    calls: dict[str, dict[str, Any]] = {}
    artifacts: dict[str, dict[str, Any]] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        container_type = str(event.get("type") or "")
        event_digest = hashlib.sha256(line.encode("utf-8", errors="replace")).hexdigest()
        nodes = [event]
        nodes.extend(event[key] for key in ("item", "part", "msg") if isinstance(event.get(key), dict))
        for node in nodes:
            node_type = str(node.get("type") or "")
            combined_type = f"{container_type}:{node_type}".strip(":")
            lowered = combined_type.lower()
            if not any(marker in lowered for marker in TOOL_EVENT_MARKERS):
                continue
            call_id_raw = node.get("call_id") or node.get("tool_call_id") or node.get("id")
            name = _tool_name(node, combined_type)
            call_id = _safe_token(call_id_raw or f"{name}-{event_digest[:16]}")
            record = calls.get(call_id, {
                "call_id": call_id,
                "provider": _safe_token(provider),
                "tool": name,
                "event_type": _safe_token(node_type or container_type or "tool_event"),
                "status": "running",
                "event_sha256": event_digest,
            })
            status = _tool_status(node, container_type)
            if status == "failed" or (status == "succeeded" and record["status"] != "failed"):
                record["status"] = status
            record["event_sha256"] = event_digest
            arguments = next((node.get(key) for key in ("arguments", "args", "params", "input") if key in node), None)
            result = next((node.get(key) for key in ("result", "output", "tool_result") if key in node), None)
            if arguments is not None:
                record["input_sha256"] = hashlib.sha256(_stable_json(arguments).encode("utf-8")).hexdigest()
            if result is not None:
                record["output_sha256"] = hashlib.sha256(_stable_json(result).encode("utf-8")).hexdigest()
            calls[call_id] = record
        for reference in _collect_artifacts(event, work_dir):
            artifacts[reference["reference_sha256"]] = reference
    return (
        [calls[key] for key in sorted(calls)],
        [artifacts[key] for key in sorted(artifacts)],
    )


def tool_event_summary(tool_calls: list[dict[str, Any]] | None) -> dict[str, Any]:
    calls = tool_calls or []
    return {
        "count": len(calls),
        "event_types": sorted({_safe_token(call.get("event_type")) for call in calls}),
        "tool_names": sorted({_safe_token(call.get("tool")) for call in calls}),
        "statuses": {
            status: sum(call.get("status") == status for call in calls)
            for status in ("running", "succeeded", "failed")
        },
    }


def _normalized_aliases(value: Any) -> set[str]:
    aliases: set[str] = set()
    if isinstance(value, (list, tuple, set)):
        for item in value:
            aliases |= _normalized_aliases(item)
        return aliases
    token = _safe_token(value, "")
    if token:
        aliases.add(token)
        for prefix in ("tool:", "skill:"):
            if token.startswith(prefix):
                aliases.add(token[len(prefix):])
    return aliases


def deterministic_verifier_evidence(
    text: str,
    provider_evidence: dict[str, Any] | None,
    requested_tools: list[dict[str, Any]] | None,
    tool_calls: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Return a deterministic, content-bound gateway verifier verdict."""
    requested_tools = requested_tools or []
    tool_calls = tool_calls or []
    output = str(text or "").strip()
    output_sha = hashlib.sha256(output.encode("utf-8")).hexdigest() if output else ""
    provider_bound = bool(
        provider_evidence
        and provider_evidence.get("type") == "provider_execution"
        and provider_evidence.get("exit_code") == 0
        and provider_evidence.get("output_sha256") == output_sha
        and provider_evidence.get("output_bytes") == len(output.encode("utf-8"))
    )
    executed: dict[str, str] = {}
    for binding in requested_tools:
        binding_id = str(binding.get("id") or "")
        aliases = _normalized_aliases([
            binding_id, binding.get("name"), binding.get("_aliases", ()),
        ])
        match = next((
            call for call in tool_calls
            if call.get("status") == "succeeded"
            and bool(aliases & _normalized_aliases([call.get("tool"), call.get("capability_id")]))
        ), None)
        if match:
            executed[binding_id] = str(match.get("call_id") or "")
    checks = {
        "non_empty_answer": bool(output),
        "public_identity_preserved": not public_identity_contract_violation(output),
        "provider_evidence_bound": provider_bound,
        "requested_capabilities_available": all(item.get("status") == "available" for item in requested_tools),
        "requested_tools_executed": len(executed) == len(requested_tools),
    }
    verdict = "passed" if all(checks.values()) else "failed"
    binding_payload = {
        "output_sha256": output_sha,
        "provider_evidence_sha256": hashlib.sha256(_stable_json(provider_evidence or {}).encode("utf-8")).hexdigest(),
        "requested_tool_ids": sorted(str(item.get("id") or "") for item in requested_tools),
        "verified_tool_calls": sorted(executed.items()),
        "checks": checks,
    }
    return {
        "type": "deterministic_verifier",
        "verifier": "kolibri.gateway.contract.v1",
        "verdict": verdict,
        "binding_sha256": hashlib.sha256(_stable_json(binding_payload).encode("utf-8")).hexdigest(),
        "checks": checks,
        "requested_tool_ids": binding_payload["requested_tool_ids"],
        "verified_tool_call_ids": [call_id for _, call_id in binding_payload["verified_tool_calls"]],
    }


def skill_routing_evidence(planned_skills: list[dict[str, Any]] | None) -> dict[str, Any]:
    planned_skills = planned_skills or []
    selected = [{
        "id": _safe_token(item.get("id")),
        "name": _safe_token(item.get("name")),
        "source": item.get("source") if isinstance(item.get("source"), dict) else {},
    } for item in planned_skills]
    return {
        "planner": "manifest_keyword_v1",
        "selected": selected,
        "evidence": [{
            "type": "skill_manifest_binding",
            "capability_id": item["id"],
            "manifest_sha256": str(item["source"].get("manifest_sha256") or ""),
        } for item in selected],
    }


@dataclass(frozen=True)
class GatewayResult:
    status: str
    text: str
    technical: dict[str, Any]


@dataclass(frozen=True)
class FactoryCompletion:
    text: str
    error_type: str | None
    provider_model: str
    evidence: dict[str, Any] | None
    route_attempts: tuple[dict[str, Any], ...]


def _factory_control_endpoint() -> str | None:
    """Resolve exactly one configured Home Control Plane URL.

    The runtime environment is an operator-controlled trust boundary.  User
    input can never choose this endpoint, redirects are disabled, embedded
    credentials are forbidden, and historical main/primary authorities fail
    closed.  Mesh-manifest discovery remains the release/bootstrap layer's
    responsibility; the backend consumes the single resolved URL.
    """

    raw_values = [
        os.environ.get("KOLIBRI_FACTORY_CONTROL_URL", ""),
        os.environ.get("KOLIBRI_FACTORY_CONTROL_URLS", ""),
    ]
    endpoints: list[str] = []
    for raw_value in raw_values:
        for candidate in raw_value.split(","):
            normalized = candidate.strip().rstrip("/")
            if normalized and normalized not in endpoints:
                endpoints.append(normalized)
    if len(endpoints) != 1:
        return None
    try:
        return resolve_home_control_plane_url(control_url=endpoints[0])
    except Exception:
        return None


def _factory_control_configured() -> bool:
    """Return whether an operator attempted to configure factory routing.

    This is intentionally separate from endpoint validation.  A malformed,
    duplicated or legacy authority must fail closed; it must never turn into a
    signal to execute the same customer prompt directly on the backend host.
    """

    return any(
        candidate.strip()
        for name in ("KOLIBRI_FACTORY_CONTROL_URL", "KOLIBRI_FACTORY_CONTROL_URLS")
        for candidate in os.environ.get(name, "").split(",")
    )


def _production_runtime() -> bool:
    """Return whether direct backend runners must be disabled unconditionally."""

    return os.environ.get("KOLIBRI_ENV", "development").strip().lower() in {
        "prod", "production",
    }


def _factory_node_ref(node_id: str) -> str:
    return f"node:{hashlib.sha256(node_id.encode('utf-8')).hexdigest()[:16]}"


class ProviderGateway:
    def __init__(
        self,
        provider_order: tuple[str, ...] | None = None,
        timeout: int | None = None,
        model_overrides: dict[str, tuple[str, ...]] | None = None,
    ):
        configured = tuple(
            item.strip().lower()
            for item in os.environ.get(
                "KOLIBRI_PROVIDER_ORDER", ",".join(DEFAULT_PROVIDER_ORDER)
            ).split(",")
            if item.strip().lower() in SUPPORTED_PROVIDERS
        )
        requested_order = provider_order or configured or DEFAULT_PROVIDER_ORDER
        self.provider_order = tuple(provider for provider in requested_order if provider in SUPPORTED_PROVIDERS)
        if _factory_control_configured() or _production_runtime():
            # A configured factory boundary is an execution-policy boundary,
            # not merely the first preference in a list.  Mimo -> Codex
            # fallback happens as separate fenced Home tasks inside the
            # factory route.  Direct CLI/HTTP providers on the public backend
            # are forbidden, including when Home is invalid or unavailable.
            # Production also fails closed when the endpoint was accidentally
            # omitted: missing configuration must not become direct execution.
            self.provider_order = ("factory",)
        elif provider_order is None and "KOLIBRI_PROVIDER_ORDER" not in os.environ:
            # Local developer/test environments without a resolved Home
            # authority keep the historical direct runner order.  Production
            # enters the fail-closed branch above as soon as any Control Plane
            # configuration is installed.
            self.provider_order = tuple(provider for provider in self.provider_order if provider != "factory")
        self.model_overrides = {
            provider: tuple(model for model in models if MODEL_ID_PATTERN.fullmatch(model))
            for provider, models in (model_overrides or {}).items()
            if provider in SUPPORTED_PROVIDERS
        }
        self.timeout = timeout or int(os.environ.get("KOLIBRI_PROVIDER_TIMEOUT", "180"))
        self.work_dir = Path(os.environ.get("KOLIBRI_PROVIDER_WORK_DIR", str(DATA_DIR / "provider-work")))
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def available(self) -> dict[str, bool]:
        return {
            provider: (
                _factory_control_endpoint() is not None
                if provider == "factory"
                else self._local_endpoint() is not None
                if provider == "local"
                else bool(os.environ.get("DEEPSEEK_API_KEY")) and self._deepseek_endpoint() is not None
                if provider == "deepseek"
                else self._binary(provider) is not None
            )
            for provider in self.provider_order
        }

    @staticmethod
    def _binary(provider: str) -> str | None:
        explicit = os.environ.get(f"KOLIBRI_{provider.upper()}_BIN")
        if explicit:
            path = Path(explicit).expanduser()
            return str(path) if path.is_file() and os.access(path, os.X_OK) else None
        return shutil.which(provider)

    @staticmethod
    def _models(provider: str) -> tuple[str, ...]:
        if provider == "factory":
            configured = os.environ.get("KOLIBRI_FACTORY_PROVIDER_RUNNERS", "mimo,codex")
            return tuple(dict.fromkeys(
                item.strip().lower()
                for item in configured.split(",")
                if item.strip().lower() in FACTORY_SUPPORTED_RUNNERS
            ))
        if provider == "mimo":
            configured_models = (os.environ.get("KOLIBRI_MIMO_MODEL", "mimo/mimo-auto"),)
            return tuple(item for item in configured_models if MODEL_ID_PATTERN.fullmatch(item))
        if provider == "codex":
            explicit = os.environ.get("KOLIBRI_CODEX_MODEL")
            configured = explicit or os.environ.get("KOLIBRI_CODEX_MODELS", ",".join(DEFAULT_CODEX_MODELS))
            return tuple(dict.fromkeys(
                item.strip() for item in configured.split(",")
                if item.strip() and MODEL_ID_PATTERN.fullmatch(item.strip())
            ))
        if provider == "local":
            configured = (
                os.environ.get("KOLIBRI_LOCAL_LLM_MODEL")
                or os.environ.get("KOLIBRI_LLM_MODEL")
                or "qwen3.6-plus"
            ).strip()
            return (configured,) if LOCAL_MODEL_ID_PATTERN.fullmatch(configured) else ()
        if provider == "deepseek":
            configured = (
                os.environ.get("KOLIBRI_DEEPSEEK_MODEL")
                or os.environ.get("DEEPSEEK_MODEL")
                or "deepseek-v4-pro"
            ).strip()
            return (configured,) if LOCAL_MODEL_ID_PATTERN.fullmatch(configured) else ()
        return ()

    def _factory_request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        endpoint = _factory_control_endpoint()
        if endpoint is None:
            return None, "factory_control_endpoint_invalid"
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        token = os.environ.get("KOLIBRI_FACTORY_CONTROL_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            f"{endpoint}{path}", data=body, headers=headers, method=method,
        )
        opener = urllib.request.build_opener(_NoRedirect())
        request_timeout = max(0.05, min(float(timeout or self.timeout), float(self.timeout)))
        try:
            configured_limit = int(os.environ.get("KOLIBRI_FACTORY_MAX_RESPONSE_BYTES", "2097152"))
        except ValueError:
            configured_limit = 2097152
        max_bytes = min(max(configured_limit, 1024), 8 * 1024 * 1024)
        try:
            with opener.open(request, timeout=request_timeout) as response:
                if response.status == 204:
                    return {}, None
                if response.status < 200 or response.status >= 300:
                    return None, "factory_control_request_failed"
                raw = response.read(max_bytes + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            if status == 401:
                return None, "factory_control_auth_failed"
            if status == 403:
                return None, "factory_control_access_denied"
            if status == 429:
                return None, "provider_usage_limit"
            return None, "factory_control_request_failed"
        except (urllib.error.URLError, TimeoutError, OSError):
            return None, "factory_control_unavailable"
        if len(raw) > max_bytes:
            return None, "factory_control_response_too_large"
        if not raw:
            return {}, None
        try:
            parsed = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError):
            return None, "factory_control_response_invalid"
        if not isinstance(parsed, dict):
            return None, "factory_control_response_invalid"
        return parsed, None

    def _factory_candidates(self, runner: str) -> tuple[list[dict[str, Any]], str | None]:
        payload, error_type = self._factory_request("GET", "/v1/nodes?scope=active&limit=250")
        if error_type or not isinstance(payload, dict):
            return [], error_type or "factory_control_response_invalid"
        nodes = payload.get("nodes")
        if not isinstance(nodes, list):
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            nodes = data.get("nodes")
        if not isinstance(nodes, list):
            return [], "factory_control_response_invalid"
        try:
            max_age = max(5.0, min(float(os.environ.get("KOLIBRI_FACTORY_NODE_MAX_AGE", "45")), 300.0))
        except ValueError:
            max_age = 45.0
        candidates: list[dict[str, Any]] = []
        seen_node_ids: set[str] = set()
        for raw_node in nodes:
            if not isinstance(raw_node, dict):
                continue
            node_id = _safe_token(raw_node.get("node_id") or raw_node.get("id"), "")
            if not node_id or node_id in seen_node_ids:
                continue
            seen_node_ids.add(node_id)
            capabilities = {
                str(item).strip().lower()
                for item in raw_node.get("capabilities", [])
                if isinstance(item, str)
            }
            # Home remains the task authority, not an inference worker.  This
            # rule is capability/role based, so no physical worker catalog is
            # embedded in the gateway.
            role = str(raw_node.get("role") or "").strip().lower()
            if role == "control_plane" or "control_plane" in capabilities or "home" in capabilities:
                continue
            if raw_node.get("draining") or raw_node.get("active_task"):
                continue
            if "schedulable" in raw_node and raw_node.get("schedulable") is not True:
                continue
            if str(raw_node.get("health") or "").lower() != "online":
                continue
            freshness = str(raw_node.get("freshness") or raw_node.get("freshness_status") or "").lower()
            try:
                age = float(raw_node.get("heartbeat_age_seconds"))
            except (TypeError, ValueError):
                age = max_age + 1
            if freshness not in {"fresh", "online"} or age < 0 or age > max_age:
                continue
            required_capability = f"runner:{runner}"
            if required_capability not in capabilities:
                continue
            runners = raw_node.get("runners") if isinstance(raw_node.get("runners"), dict) else {}
            runner_record = runners.get(runner)
            if isinstance(runner_record, dict):
                runner_status = str(runner_record.get("status") or "").lower()
            else:
                runner_status = str(runner_record or "").lower()
            if runner_status != "available":
                continue
            # Binary discovery alone is not an execution contract.  Legacy
            # Agent Hosts put prompts in argv and can grant danger-full-access;
            # never send customer input there.  A worker becomes eligible only
            # after the uniform Agent Host release advertises every safe bound.
            if not isinstance(runner_record, dict) or not (
                runner_record.get("factory_provider_contract") == FACTORY_RUNNER_CONTRACT
                and runner_record.get("prompt_transport") in {"stdin", "file"}
                and runner_record.get("sandbox") == "read-only"
                and runner_record.get("worktree_scoped") is True
                and str(runner_record.get("output_format") or "").lower() in {"json", "jsonl"}
            ):
                continue
            hostname = _safe_token(raw_node.get("hostname") or raw_node.get("display_name"), "")
            candidates.append({
                "node_id": node_id,
                "hostname": hostname,
                "heartbeat_age_seconds": age,
            })
        candidates.sort(key=lambda item: (
            item["hostname"] in {"", "kolibri", "localhost"},
            item["heartbeat_age_seconds"],
            item["node_id"],
        ))
        if not candidates:
            return [], "factory_no_fresh_capable_worker"
        try:
            max_attempts = max(1, min(int(os.environ.get("KOLIBRI_FACTORY_MAX_NODE_ATTEMPTS", "3")), 8))
        except ValueError:
            max_attempts = 3
        return candidates[:max_attempts], None

    @staticmethod
    def _factory_task_error(task: dict[str, Any]) -> str:
        result = task.get("result") if isinstance(task.get("result"), dict) else {}
        error_type = str(task.get("error_type") or result.get("error_type") or "").lower()
        if error_type in {"runner_policy_blocked", "provider_risk_control"}:
            return "provider_risk_control"
        if error_type in {"runner_auth_blocked", "runner_auth_failed", "provider_auth_failed"}:
            return "provider_auth_failed"
        if error_type in {"runner_access_denied", "provider_access_denied"}:
            return "provider_access_denied"
        if error_type in {"runner_unavailable", "provider_runner_missing"}:
            return "provider_runner_missing"
        if error_type in {"lease_expired", "provider_timeout"}:
            return "provider_timeout"
        if error_type in {"provider_usage_limit", "rate_limited"}:
            return "provider_usage_limit"
        if error_type == "runtime_error" and "without text response" in str(task.get("error") or "").lower():
            return "provider_empty_output"
        return "provider_runtime_failed"

    @staticmethod
    def _verify_factory_task(
        task: dict[str, Any], *, node_id: str, runner: str,
    ) -> tuple[str, dict[str, Any] | None, str | None]:
        result = task.get("result") if isinstance(task.get("result"), dict) else {}
        attempt_id = str(task.get("attempt_id") or "")
        lease_owner = str(task.get("lease_owner") or "")
        lease_node, separator, lease_agent = lease_owner.partition(":")
        response_text = result.get("response")
        response_text = response_text.strip() if isinstance(response_text, str) else ""
        write_scope_violations = result.get("write_scope_violations")
        checks = {
            "task_completed": str(task.get("state") or "").lower() == "completed",
            "result_completed": str(result.get("status") or "").lower() == "completed",
            "attempt_fenced": bool(attempt_id) and str(result.get("attempt_id") or "") == attempt_id,
            "lease_fenced": bool(separator and lease_agent) and lease_node == node_id,
            "node_bound": str(result.get("node_id") or "") == node_id,
            "agent_bound": str(result.get("agent_id") or "") == lease_agent,
            "runner_bound": str(result.get("runner") or "").lower() == runner,
            "non_empty_answer": bool(response_text),
            "no_scope_violation": not bool(write_scope_violations),
            "no_product_code_change": not bool(result.get("product_code_changed")),
            "no_terminal_error": not task.get("error_type"),
        }
        if not all(checks.values()):
            return "", None, "factory_evidence_invalid"
        output_sha = hashlib.sha256(response_text.encode("utf-8")).hexdigest()
        evidence = {
            "type": "provider_execution",
            "provider": "factory",
            "provider_model": runner,
            "provider_runner": runner,
            "route_transport": "home_control_plane",
            "task_id": _safe_token(task.get("task_id")),
            # The Control Plane retains the physical node ID.  Public response
            # provenance gets only a stable opaque reference so the gateway
            # cannot leak internal topology.
            "node_ref": _factory_node_ref(node_id),
            "attempt_id": _safe_token(attempt_id),
            "task_state": "completed",
            "result_status": "completed",
            "fence_verified": True,
            "checks": checks,
            "exit_code": 0,
            "output_sha256": output_sha,
            "output_bytes": len(response_text.encode("utf-8")),
            "completion_signal": "fenced_non_empty_assistant_output",
        }
        return response_text, evidence, None

    def _run_factory_candidate(
        self,
        *,
        prompt: str,
        response_id: str,
        runner: str,
        node_id: str,
        timeout_budget: float,
    ) -> tuple[str, dict[str, Any] | None, str | None, dict[str, Any]]:
        digest = hashlib.sha256(
            f"{response_id}\0{runner}\0{node_id}\0{prompt}".encode("utf-8")
        ).hexdigest()
        task_id = f"KOL-PROVIDER-{_safe_token(response_id)[:32]}-{digest[:16]}"
        idempotency_key = f"factory-provider:{digest}"
        try:
            task_timeout = max(
                0.1,
                min(
                    float(os.environ.get("KOLIBRI_FACTORY_TASK_TIMEOUT", "45")),
                    float(self.timeout),
                    timeout_budget,
                ),
            )
            poll_interval = max(
                0.01,
                min(float(os.environ.get("KOLIBRI_FACTORY_POLL_INTERVAL", "0.5")), 5.0),
            )
        except ValueError:
            task_timeout, poll_interval = min(45.0, float(self.timeout)), 0.5
        envelope = {
            "task_id": task_id,
            "idempotency_key": idempotency_key,
            "kind": "owner_remote_task",
            "target_node": node_id,
            "required_capability": f"runner:{runner}",
            "runner": runner,
            "objective": prompt,
            "write_scope": [],
            "constraints": {
                "read_only": True,
                "max_wall_seconds": max(1, int(task_timeout)),
                "network": "provider_managed_only",
            },
            "max_retries": 0,
            "fallback_allowed": False,
            "source": {
                "kind": "kolibri_provider_gateway",
                "control_plane": "home",
                "response_id": _safe_token(response_id),
                "identity_contract": PUBLIC_IDENTITY_CONTRACT_VERSION,
            },
        }
        task, error_type = self._factory_request(
            "POST", "/v1/tasks", payload=envelope, timeout=min(task_timeout, 10.0),
        )
        route_record = {
            "node_ref": _factory_node_ref(node_id),
            "runner": runner,
            "task_id": _safe_token(task_id),
            "idempotency_sha256": hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest(),
        }
        if error_type or not isinstance(task, dict):
            route_record.update({"status": "failed", "error_type": error_type or "factory_control_response_invalid"})
            return "", None, route_record["error_type"], route_record
        returned_task_id = str(task.get("task_id") or "")
        if returned_task_id != task_id:
            route_record.update({"status": "failed", "error_type": "factory_evidence_invalid"})
            return "", None, "factory_evidence_invalid", route_record
        deadline = time.monotonic() + task_timeout
        current = task
        while True:
            state = str(current.get("state") or "").lower()
            if state in FACTORY_TERMINAL_STATES:
                if state == "completed":
                    text, evidence, verification_error = self._verify_factory_task(
                        current, node_id=node_id, runner=runner,
                    )
                    if verification_error:
                        route_record.update({"status": "failed", "error_type": verification_error})
                        return "", None, verification_error, route_record
                    route_record.update({
                        "status": "succeeded",
                        "attempt_id": _safe_token(current.get("attempt_id")),
                    })
                    return text, evidence, None, route_record
                failure = self._factory_task_error(current)
                route_record.update({
                    "status": "failed",
                    "error_type": failure,
                    "attempt_id": _safe_token(current.get("attempt_id")),
                })
                return "", None, failure, route_record
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._factory_request(
                    "POST",
                    f"/v1/tasks/{quote(task_id, safe='')}/cancel",
                    payload={"reason": "factory_provider_poll_timeout"},
                    timeout=min(5.0, float(self.timeout)),
                )
                route_record.update({"status": "failed", "error_type": "provider_timeout"})
                return "", None, "provider_timeout", route_record
            time.sleep(min(poll_interval, remaining))
            current, error_type = self._factory_request(
                "GET", f"/v1/tasks/{quote(task_id, safe='')}", timeout=min(remaining, 10.0),
            )
            if error_type or not isinstance(current, dict):
                route_record.update({
                    "status": "failed",
                    "error_type": error_type or "factory_control_response_invalid",
                })
                return "", None, route_record["error_type"], route_record

    def _run_factory_completion(
        self, prompt: str, runner: str, response_id: str,
    ) -> FactoryCompletion:
        candidates, error_type = self._factory_candidates(runner)
        if error_type:
            return FactoryCompletion("", error_type, runner, None, ())
        try:
            route_timeout = max(
                0.1,
                min(float(os.environ.get("KOLIBRI_FACTORY_ROUTE_TIMEOUT", str(self.timeout))), float(self.timeout)),
            )
        except ValueError:
            route_timeout = float(self.timeout)
        deadline = time.monotonic() + route_timeout
        route_attempts: list[dict[str, Any]] = []
        last_error = "factory_no_fresh_capable_worker"
        for candidate in candidates:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                last_error = "provider_timeout"
                break
            text, evidence, error_type, route_record = self._run_factory_candidate(
                prompt=prompt,
                response_id=response_id,
                runner=runner,
                node_id=str(candidate["node_id"]),
                timeout_budget=remaining,
            )
            route_attempts.append(route_record)
            if text and evidence and error_type is None:
                return FactoryCompletion(text, None, runner, evidence, tuple(route_attempts))
            last_error = error_type or "provider_runtime_failed"
            if last_error in {
                "factory_control_access_denied", "factory_control_auth_failed",
                "factory_control_endpoint_invalid", "factory_control_unavailable",
            }:
                break
        return FactoryCompletion("", last_error, runner, None, tuple(route_attempts))

    @staticmethod
    def _local_endpoint() -> str | None:
        endpoint = (
            os.environ.get("KOLIBRI_LOCAL_LLM_ENDPOINT")
            or os.environ.get("KOLIBRI_LLM_ENDPOINT")
            or ""
        ).strip()
        if not endpoint:
            return None
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != "/v1/chat/completions"
        ):
            return None
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            return None
        if not address.is_loopback:
            return None
        return endpoint

    @staticmethod
    def _deepseek_endpoint() -> str | None:
        endpoint = os.environ.get(
            "KOLIBRI_DEEPSEEK_ENDPOINT",
            "https://api.deepseek.com/chat/completions",
        ).strip()
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https"
            or parsed.hostname != DEEPSEEK_API_HOST
            or parsed.port not in {None, 443}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != "/chat/completions"
        ):
            return None
        return endpoint

    def _run_openai_compatible_completion(
        self,
        *,
        endpoint: str,
        api_key: str | None,
        prompt: str,
        model: str,
    ) -> tuple[str, str | None]:
        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        opener = urllib.request.build_opener(_NoRedirect())
        max_bytes = int(os.environ.get("KOLIBRI_LOCAL_LLM_MAX_RESPONSE_BYTES", "8388608"))
        try:
            with opener.open(request, timeout=self.timeout) as response:
                if response.status != 200:
                    return "", "provider_runtime_failed"
                raw = response.read(max_bytes + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                return "", "provider_auth_failed" if exc.code == 401 else "provider_access_denied"
            if exc.code == 429:
                return "", "provider_usage_limit"
            return "", "provider_runtime_failed"
        except (urllib.error.URLError, TimeoutError, OSError):
            return "", "provider_runtime_failed"
        if len(raw) > max_bytes:
            return "", "provider_output_too_large"
        try:
            payload = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError):
            return "", "provider_response_invalid"
        choices = payload.get("choices") if isinstance(payload, dict) else None
        first = choices[0] if isinstance(choices, list) and choices else {}
        message = first.get("message") if isinstance(first, dict) else {}
        text = _content_text(message.get("content") if isinstance(message, dict) else "").strip()
        return (text, None) if text else ("", "provider_empty_output")

    def _run_local_completion(self, prompt: str, model: str) -> tuple[str, str | None]:
        endpoint = self._local_endpoint()
        if endpoint is None:
            return "", "provider_endpoint_invalid"
        api_key = os.environ.get("KOLIBRI_LOCAL_LLM_API_KEY") or os.environ.get("KOLIBRI_LLM_API_KEY")
        return self._run_openai_compatible_completion(
            endpoint=endpoint,
            api_key=api_key,
            prompt=prompt,
            model=model,
        )

    def _run_deepseek_completion(self, prompt: str, model: str) -> tuple[str, str | None]:
        endpoint = self._deepseek_endpoint()
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if endpoint is None:
            return "", "provider_endpoint_invalid"
        if not api_key:
            return "", "provider_auth_failed"
        return self._run_openai_compatible_completion(
            endpoint=endpoint,
            api_key=api_key,
            prompt=prompt,
            model=model,
        )

    def _route_models(self, provider: str) -> tuple[str, ...]:
        return self.model_overrides.get(provider) or self._models(provider)

    @staticmethod
    def _provider_supports_tools(provider: str, requested_tools: list[dict[str, Any]]) -> bool:
        return all(provider in tuple(item.get("_providers") or ()) for item in requested_tools)

    @staticmethod
    def _provider_supports_skills(provider: str, planned_skills: list[dict[str, Any]]) -> bool:
        # The Home factory transports skill plans as audited planning context;
        # the selected Mimo/Codex worker performs the actual workflow.  A skill
        # manifest therefore must not make the single canonical factory route
        # unavailable merely because its local catalog predates the factory
        # provider name.
        if provider == "factory":
            return True
        return all(provider in tuple(item.get("_providers") or ()) for item in planned_skills)

    def _command(
        self, provider: str, binary: str, response_id: str,
        work_dir: Path, provider_model: str | None = None,
    ) -> tuple[list[str], str]:
        if provider == "mimo":
            provider_model = provider_model or self._route_models(provider)[0]
            return [
                binary, "run", "--pure", "--format", "json", "--model", provider_model,
                "--title", f"kolibri-response-{_safe_token(response_id)[:24]}",
            ], provider_model
        if provider == "codex":
            provider_model = provider_model or self._route_models(provider)[0]
            command = [
                binary, "exec", "--json", "--ephemeral", "--skip-git-repo-check",
                "--ignore-user-config", "--ignore-rules", "--color", "never",
                "--sandbox", "read-only", "-C", str(work_dir),
                "-c", 'shell_environment_policy.inherit="none"',
            ]
            command.extend(["--model", provider_model])
            # A literal '-' makes Codex read the prompt from stdin.  Prompt
            # content must never appear in argv/process listings.
            command.append("-")
            return command, provider_model
        raise ValueError(f"unsupported provider: {provider}")

    def generate(
        self,
        input_value: str | list[dict[str, Any]],
        instructions: str | None,
        response_id: str,
        requested_tools: list[dict[str, Any]] | None = None,
        planned_skills: list[dict[str, Any]] | None = None,
        execution_mode: str = "fast",
    ) -> GatewayResult:
        execution_mode = str(execution_mode or "fast").strip().lower()
        if execution_mode not in {"fast", "codex"}:
            return GatewayResult("failed", "", {
                "attempts": [], "error_type": "execution_mode_invalid", "evidence": [],
                "skill_routing": skill_routing_evidence(planned_skills or []),
            })
        requested_tools = requested_tools or []
        planned_skills = planned_skills or []
        skill_routing = skill_routing_evidence(planned_skills)
        if isinstance(input_value, str):
            user_text = input_value
        else:
            user_text = "\n".join(
                f"{item.get('role', 'user')}: {_content_text(item.get('content'))}"
                for item in input_value
            ).strip()
        prompt_parts = [
            PUBLIC_IDENTITY_INSTRUCTION,
            *[part for part in [instructions, user_text] if part],
        ]
        if planned_skills:
            planned_names = [f"${_safe_token(item.get('name'))}" for item in planned_skills]
            prompt_parts.append(
                "Kolibri internal skill plan: apply the installed Codex skill workflows when relevant: "
                f"{', '.join(planned_names)}. Skills are prompt/planner capabilities, not native tool calls."
            )
        if requested_tools:
            public_tools = [
                {key: value for key, value in item.items() if not key.startswith("_")}
                for item in requested_tools
            ]
            prompt_parts.append(
                "Kolibri tool contract: use every requested capability through its native runner tool "
                "interface, emit the native JSONL tool-call/result events, and then provide a non-empty "
                f"assistant answer. Requested capabilities: {_stable_json(public_tools)}"
            )
        prompt = "\n\n".join(prompt_parts).strip()
        if not prompt:
            return GatewayResult("failed", "", {
                "attempts": [], "error_type": "empty_input", "evidence": [],
                "skill_routing": skill_routing,
            })
        max_prompt_bytes = int(os.environ.get("KOLIBRI_PROVIDER_MAX_PROMPT_BYTES", "1048576"))
        if len(prompt.encode("utf-8")) > max_prompt_bytes:
            return GatewayResult("failed", "", {
                "attempts": [], "error_type": "input_too_large", "evidence": [],
                "skill_routing": skill_routing,
            })

        attempts: list[dict[str, Any]] = []
        attempt_number = 0
        provider_order = self.provider_order
        if execution_mode == "codex" and "factory" not in provider_order and "codex" in provider_order:
            provider_order = ("codex", *tuple(provider for provider in provider_order if provider != "codex"))
        for provider in provider_order:
            if planned_skills and not self._provider_supports_skills(provider, planned_skills):
                attempt_number += 1
                attempts.append({
                    "attempt": attempt_number, "provider": provider, "status": "skipped",
                    "error_type": "planned_skill_not_supported_by_route", "duration_ms": 0,
                    "route_capability": route_capability_probe("planned_skill_not_supported_by_route"),
                })
                continue
            if requested_tools and not self._provider_supports_tools(provider, requested_tools):
                attempt_number += 1
                attempts.append({
                    "attempt": attempt_number, "provider": provider, "status": "skipped",
                    "error_type": "requested_capability_not_supported_by_route", "duration_ms": 0,
                    "route_capability": route_capability_probe("requested_capability_not_supported_by_route"),
                })
                continue
            factory_provider = provider == "factory"
            http_provider = provider in {"deepseek", "local"}
            binary = None if http_provider or factory_provider else self._binary(provider)
            if not http_provider and not factory_provider and binary is None:
                attempt_number += 1
                attempts.append({
                    "attempt": attempt_number, "provider": provider, "status": "skipped",
                    "error_type": "provider_runner_missing", "duration_ms": 0,
                    "route_capability": route_capability_probe("provider_runner_missing"),
                })
                continue
            provider_models = self._route_models(provider)
            if execution_mode == "codex" and provider == "factory" and "codex" in provider_models:
                provider_models = ("codex", *tuple(model for model in provider_models if model != "codex"))
            if not provider_models:
                attempt_number += 1
                attempts.append({
                    "attempt": attempt_number, "provider": provider, "status": "skipped",
                    "error_type": "provider_model_configuration_invalid", "duration_ms": 0,
                    "route_capability": route_capability_probe("provider_model_configuration_invalid"),
                })
                continue
            for provider_model in provider_models:
                attempt_number += 1
                started = time.monotonic()
                if factory_provider:
                    completion = self._run_factory_completion(prompt, provider_model, response_id)
                    duration_ms = int((time.monotonic() - started) * 1000)
                    identity_error = (
                        "provider_identity_contract_violation"
                        if public_identity_contract_violation(completion.text)
                        else None
                    )
                    if (
                        completion.text
                        and completion.error_type is None
                        and completion.evidence
                        and identity_error is None
                    ):
                        verifier = deterministic_verifier_evidence(
                            completion.text, completion.evidence, requested_tools, [],
                        )
                        evidence = [completion.evidence, verifier]
                        if verifier["verdict"] == "passed":
                            attempts.append({
                                "attempt": attempt_number,
                                "provider": provider,
                                "provider_model": completion.provider_model,
                                "status": "succeeded",
                                "duration_ms": duration_ms,
                                "evidence": evidence,
                                "tool_calls": [],
                                "artifact_refs": [],
                                "factory_route_attempts": list(completion.route_attempts),
                                "route_capability": route_capability_probe(succeeded=True),
                            })
                            return GatewayResult("completed", completion.text, {
                                "selected_provider": provider,
                                "selected_runner": completion.provider_model,
                                "attempts": attempts,
                                "fallback_used": attempt_number > 1,
                                "tool_calls": [],
                                "tool_event_summary": tool_event_summary([]),
                                "artifact_refs": [],
                                "verifier_evidence": verifier,
                                "evidence": evidence,
                                "skill_routing": skill_routing,
                            })
                    error_type = identity_error or completion.error_type or "factory_evidence_invalid"
                    attempts.append({
                        "attempt": attempt_number,
                        "provider": provider,
                        "provider_model": completion.provider_model,
                        "status": "failed",
                        "error_type": error_type,
                        "duration_ms": duration_ms,
                        "factory_route_attempts": list(completion.route_attempts),
                        "route_capability": route_capability_probe(error_type),
                    })
                    continue
                if http_provider:
                    completion = (
                        self._run_deepseek_completion
                        if provider == "deepseek"
                        else self._run_local_completion
                    )
                    text, error_type = completion(prompt, provider_model)
                    duration_ms = int((time.monotonic() - started) * 1000)
                    identity_error = (
                        "provider_identity_contract_violation"
                        if public_identity_contract_violation(text)
                        else None
                    )
                    if text and error_type is None and identity_error is None:
                        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                        provider_evidence = {
                            "type": "provider_execution",
                            "provider": provider,
                            "provider_model": provider_model,
                            "exit_code": 0,
                            "output_sha256": digest,
                            "output_bytes": len(text.encode("utf-8")),
                            "completion_signal": "non_empty_assistant_output",
                        }
                        verifier = deterministic_verifier_evidence(
                            text, provider_evidence, requested_tools, [],
                        )
                        evidence = [provider_evidence, verifier]
                        if verifier["verdict"] == "passed":
                            attempts.append({
                                "attempt": attempt_number,
                                "provider": provider,
                                "provider_model": provider_model,
                                "status": "succeeded",
                                "duration_ms": duration_ms,
                                "evidence": evidence,
                                "tool_calls": [],
                                "artifact_refs": [],
                                "route_capability": route_capability_probe(succeeded=True),
                            })
                            return GatewayResult("completed", text, {
                                "selected_provider": provider,
                                "attempts": attempts,
                                "fallback_used": attempt_number > 1,
                                "tool_calls": [],
                                "tool_event_summary": tool_event_summary([]),
                                "artifact_refs": [],
                                "verifier_evidence": verifier,
                                "evidence": evidence,
                                "skill_routing": skill_routing,
                            })
                    attempts.append({
                        "attempt": attempt_number,
                        "provider": provider,
                        "provider_model": provider_model,
                        "status": "failed",
                        "error_type": identity_error or error_type or "provider_runtime_failed",
                        "duration_ms": duration_ms,
                        "route_capability": route_capability_probe(error_type),
                    })
                    continue
                try:
                    with tempfile.TemporaryDirectory(
                        prefix=f"attempt-{attempt_number:04d}-",
                        dir=self.work_dir,
                    ) as attempt_path:
                        attempt_dir = Path(attempt_path)
                        attempt_dir.chmod(0o700)
                        command, provider_model = self._command(
                            provider, str(binary), response_id, attempt_dir, provider_model,
                        )
                        runner_environment = safe_runner_environment()
                        runner_environment["TMPDIR"] = str(attempt_dir)
                        completed = subprocess.run(
                            command,
                            cwd=attempt_dir,
                            input=prompt,
                            capture_output=True,
                            text=True,
                            timeout=self.timeout,
                            check=False,
                            env=runner_environment,
                            start_new_session=True,
                        )
                        tool_calls, artifact_refs = extract_tool_provenance(
                            completed.stdout, provider, attempt_dir,
                        )
                    duration_ms = int((time.monotonic() - started) * 1000)
                    text = extract_assistant_text(completed.stdout)
                    structured_error = structured_error_type(completed.stdout)
                    identity_error = (
                        "provider_identity_contract_violation"
                        if public_identity_contract_violation(text)
                        else None
                    )
                    if (
                        completed.returncode == 0
                        and text
                        and structured_error is None
                        and identity_error is None
                    ):
                        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                        provider_evidence = {
                            "type": "provider_execution",
                            "provider": provider,
                            "provider_model": provider_model,
                            "exit_code": 0,
                            "output_sha256": digest,
                            "output_bytes": len(text.encode("utf-8")),
                            "completion_signal": "non_empty_assistant_output",
                        }
                        verifier = deterministic_verifier_evidence(
                            text, provider_evidence, requested_tools, tool_calls,
                        )
                        if verifier["verdict"] == "passed":
                            evidence = [provider_evidence, verifier]
                            attempts.append({
                                "attempt": attempt_number, "provider": provider, "provider_model": provider_model,
                                "status": "succeeded", "duration_ms": duration_ms, "evidence": evidence,
                                "tool_calls": tool_calls, "artifact_refs": artifact_refs,
                                "route_capability": route_capability_probe(succeeded=True),
                            })
                            return GatewayResult("completed", text, {
                                "selected_provider": provider,
                                "attempts": attempts,
                                "fallback_used": attempt_number > 1,
                                "tool_calls": tool_calls,
                                "tool_event_summary": tool_event_summary(tool_calls),
                                "artifact_refs": artifact_refs,
                                "verifier_evidence": verifier,
                                "evidence": evidence,
                                "skill_routing": skill_routing,
                            })
                        attempts.append({
                            "attempt": attempt_number, "provider": provider, "provider_model": provider_model,
                            "status": "failed", "duration_ms": duration_ms,
                            "error_type": "tool_verification_failed",
                            "tool_calls": tool_calls, "artifact_refs": artifact_refs,
                            "verifier_evidence": verifier,
                            "route_capability": route_capability_probe("tool_verification_failed"),
                        })
                        continue
                    error_type = structured_error or identity_error or (
                        "provider_empty_output" if completed.returncode == 0
                        else classify_failure(completed.stderr, completed.returncode)
                    )
                    attempts.append({
                        "attempt": attempt_number, "provider": provider, "provider_model": provider_model,
                        "status": "failed", "error_type": error_type, "duration_ms": duration_ms,
                        "exit_code": completed.returncode,
                        "tool_calls": tool_calls, "artifact_refs": artifact_refs,
                        "route_capability": route_capability_probe(error_type),
                    })
                except subprocess.TimeoutExpired:
                    attempts.append({
                        "attempt": attempt_number, "provider": provider, "provider_model": provider_model,
                        "status": "failed", "error_type": "provider_timeout",
                        "duration_ms": int((time.monotonic() - started) * 1000),
                        "route_capability": route_capability_probe("provider_timeout"),
                    })
        return GatewayResult("failed", "", {
            "selected_provider": None,
            "attempts": attempts,
            "fallback_used": len(attempts) > 1,
            "tool_calls": [
                call for attempt in attempts for call in (attempt.get("tool_calls") or [])
                if isinstance(call, dict)
            ],
            "tool_event_summary": tool_event_summary([
                call for attempt in attempts for call in (attempt.get("tool_calls") or [])
                if isinstance(call, dict)
            ]),
            "artifact_refs": [
                ref for attempt in attempts for ref in (attempt.get("artifact_refs") or [])
                if isinstance(ref, dict)
            ],
            "evidence": [],
            "error_type": attempts[-1].get("error_type", "provider_unavailable") if attempts else "provider_unavailable",
            "skill_routing": skill_routing,
        })


_gateway: ProviderGateway | Any | None = None


def configure_provider_gateway(gateway: Any) -> Any:
    global _gateway
    _gateway = gateway
    return gateway


def get_provider_gateway() -> ProviderGateway | Any:
    global _gateway
    if _gateway is None:
        _gateway = ProviderGateway()
    return _gateway
