#!/usr/bin/env python3
"""Thin ChatGPT Action gateway for Kolibri Factory.

The gateway is an adapter over the Factory Control API. It does not execute
shell commands, bypass the Control Plane, or perform privileged operations.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib import error, request
from urllib.parse import quote, urlparse


DEFAULT_CONTROL_URLS = (
    "http://10.99.0.10:9101",
    "http://10.99.0.2:9101",
    "http://10.99.0.1:9101",
)
AUTH_TOKEN_ENV = "KOLIBRI_CHATGPT_ACTION_TOKEN"
CONTROL_URLS_ENV = "KOLIBRI_FACTORY_CONTROL_URLS"
CONTROL_URL_ENV = "KOLIBRI_FACTORY_CONTROL_URL"
TIMEOUT = float(os.getenv("KOLIBRI_CHATGPT_ACTION_TIMEOUT", "4"))
REPAIR_CONTROL_PLANE_TASK = "P0_REPAIR_CONTROL_PLANE_API"
DANGEROUS_ACTIONS = (
    "reboot",
    "restart",
    "systemctl",
    "firewall",
    "iptables",
    "ufw",
    "delete",
    "rm -rf",
    "git reset",
    "git clean",
    "force push",
    "merge",
    "token",
    "secret",
    "authorized_keys",
    "redis flush",
)


def utc_ms() -> int:
    return int(time.time() * 1000)


def request_id(prefix: str = "req") -> str:
    return f"{prefix}-{utc_ms()}-{uuid.uuid4().hex[:8]}"


def read_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    if not raw:
        return {}
    return json.loads(raw)


def write_json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def token_configured() -> bool:
    return bool(os.getenv(AUTH_TOKEN_ENV))


def authorized(headers: Any) -> bool:
    token = os.getenv(AUTH_TOKEN_ENV)
    if not token:
        return True
    return headers.get("Authorization") == f"Bearer {token}"


def safe_error(exc: Exception) -> str:
    text = str(exc)
    for marker in ("Authorization", "Bearer", "token", "secret", "password"):
        text = text.replace(marker, "[redacted]")
    return text[:300]


def control_urls() -> list[str]:
    raw = os.getenv(CONTROL_URLS_ENV)
    if raw:
        urls = [part.strip().rstrip("/") for part in raw.split(",") if part.strip()]
    else:
        single = os.getenv(CONTROL_URL_ENV)
        urls = [single.strip().rstrip("/")] if single else list(DEFAULT_CONTROL_URLS)
    return list(dict.fromkeys(url for url in urls if url))


def response_envelope(
    *,
    status: str,
    request_id_value: str | None = None,
    task_id: str = "",
    control_plane_used: str = "",
    artifacts: list[Any] | None = None,
    blocked_reason: str = "",
    fallback_nodes: list[Any] | None = None,
    repair_task: Any = "",
    next_action: str = "",
    data: Any | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "request_id": request_id_value or request_id(),
        "task_id": task_id,
        "control_plane_used": control_plane_used,
        "artifacts": artifacts or [],
        "blocked_reason": blocked_reason,
        "fallback_nodes": fallback_nodes or [],
        "repair_task": repair_task,
        "next_action": next_action,
    }
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return payload


def blocked(
    reason: str,
    *,
    request_id_value: str | None = None,
    repair_task: Any = REPAIR_CONTROL_PLANE_TASK,
    detail: str = "",
    task_id: str = "",
    control_plane_used: str = "",
    fallback_nodes: list[Any] | None = None,
    next_action: str = "repair Control Plane authority/fallback and retry",
) -> dict[str, Any]:
    return response_envelope(
        status="blocked",
        request_id_value=request_id_value,
        task_id=task_id,
        control_plane_used=control_plane_used,
        blocked_reason=reason,
        fallback_nodes=fallback_nodes or [],
        repair_task=repair_task,
        next_action=next_action,
        data={"detail": detail} if detail else None,
    )


def approval_required(body: dict[str, Any], reason: str = "approval_required") -> dict[str, Any]:
    approval_id = body.get("approval_id") or request_id("approval")
    return response_envelope(
        status="blocked",
        request_id_value=approval_id,
        blocked_reason=reason,
        repair_task={"kind": "owner_approval_required"},
        next_action="owner must approve explicitly before privileged execution",
        data={
            "approval_id": approval_id,
            "requested_action": body.get("action") or body.get("kind") or "factory_action",
            "dangerous": True,
        },
    )


def contains_dangerous_action(body: dict[str, Any]) -> bool:
    text = json.dumps(body, ensure_ascii=False).lower()
    return any(marker in text for marker in DANGEROUS_ACTIONS)


def _http_json(
    base_url: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    timeout: float = TIMEOUT,
) -> tuple[int, dict[str, Any]]:
    url = f"{base_url}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return resp.status, json.loads(raw) if raw else {}


def control_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    timeout: float = TIMEOUT,
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    failed_candidates: list[dict[str, str]] = []
    urls = control_urls()
    for base_url in urls:
        try:
            status, payload = _http_json(base_url, method, path, body, timeout)
            return status, payload, {"control_plane_used": base_url, "failed_candidates": failed_candidates}
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {"error": "control_plane_http_error", "detail": raw[:300]}
            if exc.code < 500:
                return exc.code, payload, {"control_plane_used": base_url, "failed_candidates": failed_candidates}
            failed_candidates.append({"url": base_url, "reason": f"http_{exc.code}"})
        except Exception as exc:
            failed_candidates.append({"url": base_url, "reason": safe_error(exc)})
    return 503, blocked(
        "control_plane_unavailable",
        fallback_nodes=failed_candidates,
        repair_task=REPAIR_CONTROL_PLANE_TASK,
        next_action="restore one Control Plane endpoint or update KOLIBRI_FACTORY_CONTROL_URLS",
    ), {"control_plane_used": "", "failed_candidates": failed_candidates}


def health_selection(timeout: float = 2.0) -> tuple[int, dict[str, Any], dict[str, Any]]:
    return control_request("GET", "/v1/health", timeout=timeout)


def task_id_from_payload(payload: dict[str, Any]) -> str:
    if payload.get("task_id"):
        return str(payload["task_id"])
    data = payload.get("data")
    if isinstance(data, dict):
        task = data.get("task")
        if isinstance(task, dict) and task.get("task_id"):
            return str(task["task_id"])
    return ""


def safe_factory_canary_envelope(body: dict[str, Any]) -> dict[str, Any]:
    canary_id = body.get("task_id") or f"START_FACTORY_CANARY_{utc_ms()}_{uuid.uuid4().hex[:6]}"
    objective = (
        "Read README.md and current Kolibri Factory source-of-truth docs. "
        "Return a short report: what Kolibri AI is, active components, "
        "current Start Factory blocker, and the next P0 task. Produce a "
        "content-bearing collectable artifact. Do not change product code."
    )
    return {
        "task_id": canary_id,
        "idempotency_key": body.get("idempotency_key") or canary_id,
        "kind": "owner_remote_task",
        "source": "chatgpt_action_gateway",
        "command_node": "owner_chat",
        "requested_role": "remote_agent",
        "autopilot": body.get("autopilot", "A1"),
        "runner": body.get("runner", "codex"),
        "target_node": body.get("target_node"),
        "required_capability": body.get("required_capability") or "generic_implementation",
        "fallback_allowed": True,
        "write_scope": [],
        "constraints": {
            "read_only": True,
            "no_product_code_changes": True,
            "no_push": True,
            "no_secrets": True,
            "collectable_artifact_required": True,
        },
        "objective": objective,
        "goal": objective,
        "artifact_contract": {
            "collectable": True,
            "content_bearing": True,
            "expected_paths": ["docs/agent/runs/*/START_FACTORY_CANARY_REPORT.md"],
        },
    }


def route(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    body = body or {}
    rid = request_id()
    if path == "/v1/action/health" and method == "GET":
        status, control, meta = health_selection(timeout=2)
        reachable = status < 500
        return 200, response_envelope(
            status="completed" if reachable else "blocked",
            request_id_value=rid,
            control_plane_used=meta.get("control_plane_used", ""),
            fallback_nodes=meta.get("failed_candidates", []),
            blocked_reason="" if reachable else "control_plane_unavailable",
            repair_task="" if reachable else REPAIR_CONTROL_PLANE_TASK,
            next_action="call /v1/factory/start for safe canary" if reachable else "repair Control Plane fallback",
            data={
                "gateway": "kolibri-chatgpt-action",
                "token_present": token_configured(),
                "control_status": control.get("status") or control.get("error") or control.get("blocked_reason"),
                "configured_control_urls": control_urls(),
            },
        )
    if path == "/v1/factory/start" and method == "POST":
        if contains_dangerous_action(body):
            return 202, approval_required(body, "dangerous_action_requires_owner_approval")
        health_status, health, meta = health_selection(timeout=2)
        if health_status >= 500:
            return 503, blocked(
                "factory_control_unreachable",
                request_id_value=rid,
                detail=health.get("detail", "") or health.get("blocked_reason", ""),
                fallback_nodes=meta.get("failed_candidates", []),
            )
        if body.get("mode") == "dry_run" or body.get("submit_canary") is False:
            return 200, response_envelope(
                status="completed",
                request_id_value=rid,
                control_plane_used=meta.get("control_plane_used", ""),
                fallback_nodes=meta.get("failed_candidates", []),
                next_action="submit a bounded task through /v1/tasks/submit",
                data={"mode": "dry_run", "control_plane": health},
            )
        task_body = safe_factory_canary_envelope(body)
        task_status, task_payload, task_meta = control_request("POST", "/v1/agents/tasks", task_body)
        task_id = task_id_from_payload(task_payload)
        if task_status >= 500:
            return 503, blocked(
                "factory_canary_submit_failed",
                request_id_value=rid,
                detail=task_payload.get("detail", "") or task_payload.get("blocked_reason", ""),
                fallback_nodes=task_meta.get("failed_candidates", []),
            )
        return 202 if task_status < 300 else task_status, response_envelope(
            status="running" if task_status < 300 else "blocked",
            request_id_value=rid,
            task_id=task_id,
            control_plane_used=task_meta.get("control_plane_used", ""),
            fallback_nodes=task_meta.get("failed_candidates", []),
            blocked_reason="" if task_status < 300 else task_payload.get("blocked_reason", "task_submit_failed"),
            repair_task="" if task_status < 300 else task_payload.get("repair_task", ""),
            next_action=f"poll /v1/tasks/{quote(task_id, safe='')}/status" if task_id else "inspect task submit response",
            data={"factory_run_id": body.get("factory_run_id") or request_id("factory"), "control_plane": health, "task": task_payload},
        )
    if path == "/v1/director/tick" and method == "POST":
        if contains_dangerous_action(body):
            return 202, approval_required(body, "dangerous_action_requires_owner_approval")
        return 200, response_envelope(
            status="completed",
            request_id_value=rid,
            next_action="call /v1/fleet/status and /v1/queue/status",
            data={
                "tick_id": body.get("tick_id") or request_id("tick"),
                "actions": ["read_fleet_status", "read_queue_status", "report_blockers"],
            },
        )
    if path == "/v1/fleet/status" and method == "GET":
        status, payload, meta = control_request("GET", "/v1/fleet/nodes")
        if status == 404:
            status, payload, meta = control_request("GET", "/v1/nodes")
        return status, response_envelope(
            status="completed" if status < 500 else "blocked",
            request_id_value=rid,
            control_plane_used=meta.get("control_plane_used", ""),
            fallback_nodes=meta.get("failed_candidates", []),
            blocked_reason="" if status < 500 else "fleet_status_unavailable",
            repair_task="" if status < 500 else REPAIR_CONTROL_PLANE_TASK,
            next_action="inspect queue status",
            data=payload,
        )
    if path == "/v1/queue/status" and method == "GET":
        status, payload, meta = control_request("GET", "/v1/tasks/queue/diagnostics")
        if status == 404:
            status, payload, meta = control_request("GET", "/v1/tasks")
        return status, response_envelope(
            status="completed" if status < 500 else "blocked",
            request_id_value=rid,
            control_plane_used=meta.get("control_plane_used", ""),
            fallback_nodes=meta.get("failed_candidates", []),
            blocked_reason="" if status < 500 else "queue_status_unavailable",
            repair_task="" if status < 500 else REPAIR_CONTROL_PLANE_TASK,
            next_action="submit read-only canary task when queue is healthy",
            data=payload,
        )
    if path == "/v1/tasks/submit" and method == "POST":
        if contains_dangerous_action(body):
            return 202, approval_required(body, "dangerous_action_requires_owner_approval")
        status, payload, meta = control_request("POST", "/v1/agents/tasks", body)
        task_id = task_id_from_payload(payload)
        return status, response_envelope(
            status="running" if status < 300 else "blocked",
            request_id_value=rid,
            task_id=task_id,
            control_plane_used=meta.get("control_plane_used", ""),
            fallback_nodes=meta.get("failed_candidates", []),
            blocked_reason="" if status < 300 else payload.get("blocked_reason", "task_submit_failed"),
            repair_task="" if status < 300 else payload.get("repair_task", ""),
            next_action=f"poll /v1/tasks/{quote(task_id, safe='')}/status" if task_id else "inspect task submit response",
            data=payload,
        )
    if path.startswith("/v1/tasks/") and path.endswith("/status") and method == "GET":
        task_id = path.split("/")[3]
        status, payload, meta = control_request("GET", f"/v1/agents/status/{quote(task_id, safe='')}")
        payload_status = payload.get("status") if isinstance(payload, dict) else ""
        return status, response_envelope(
            status=payload_status if payload_status in {"completed", "running", "blocked", "failed", "partial"} else ("completed" if status < 500 else "blocked"),
            request_id_value=rid,
            task_id=task_id,
            control_plane_used=meta.get("control_plane_used", ""),
            fallback_nodes=meta.get("failed_candidates", []),
            blocked_reason=payload.get("blocked_reason", "") if isinstance(payload, dict) else "",
            repair_task=payload.get("repair_task", "") if isinstance(payload, dict) else "",
            next_action=payload.get("next_action", "collect artifacts when terminal") if isinstance(payload, dict) else "",
            data=payload,
        )
    if path.startswith("/v1/tasks/") and path.endswith("/artifacts") and method == "GET":
        task_id = path.split("/")[3]
        status, payload, meta = control_request("GET", f"/v1/agents/artifacts/{quote(task_id, safe='')}")
        artifacts = payload.get("artifacts") if isinstance(payload, dict) else []
        if isinstance(artifacts, dict):
            artifacts = [artifacts]
        return status, response_envelope(
            status="completed" if status < 500 else "blocked",
            request_id_value=rid,
            task_id=task_id,
            control_plane_used=meta.get("control_plane_used", ""),
            artifacts=artifacts if isinstance(artifacts, list) else [],
            fallback_nodes=meta.get("failed_candidates", []),
            blocked_reason="" if status < 500 else "artifact_lookup_unavailable",
            repair_task="" if status < 500 else REPAIR_CONTROL_PLANE_TASK,
            next_action="open collectable artifact or inspect task blocker",
            data=payload,
        )
    if path == "/v1/github/prs" and method == "GET":
        return 200, response_envelope(
            status="partial",
            request_id_value=rid,
            blocked_reason="github_connector_not_bound_to_http_gateway",
            repair_task={"kind": "bind_github_connector_or_backend_pr_index"},
            next_action="use GitHub connector or add a Control Plane PR index endpoint",
            data={"prs": [], "note": "HTTP gateway does not read GitHub secrets or shell out to gh"},
        )
    if path == "/v1/approvals/request" and method == "POST":
        return 202, approval_required(body)
    return 404, response_envelope(
        status="blocked",
        request_id_value=rid,
        blocked_reason="not_found",
        repair_task={"kind": "verify_action_route"},
        next_action="use an endpoint declared in the OpenAPI schema",
        data={"path": path},
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _serve(self, method: str) -> None:
        if not authorized(self.headers):
            write_json(self, 401, response_envelope(status="blocked", blocked_reason="unauthorized"))
            return
        parsed = urlparse(self.path)
        try:
            body = read_body(self) if method == "POST" else {}
            status, payload = route(method, parsed.path.rstrip("/") or "/", body)
            write_json(self, status, payload)
        except Exception as exc:  # pragma: no cover - surfaced to caller
            write_json(self, 500, response_envelope(status="failed", blocked_reason="gateway_error", data={"detail": safe_error(exc)}))

    def do_GET(self) -> None:  # noqa: N802
        self._serve("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._serve("POST")


def main() -> int:
    parser = argparse.ArgumentParser(description="Kolibri ChatGPT Action gateway")
    parser.add_argument("--host", default=os.getenv("KOLIBRI_CHATGPT_ACTION_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("KOLIBRI_CHATGPT_ACTION_PORT", "9197")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"kolibri-chatgpt-action-gateway listening on {args.host}:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
