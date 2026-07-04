#!/usr/bin/env python3
"""Thin ChatGPT Action gateway for Kolibri Factory.

The gateway is intentionally an adapter over the existing Factory Control API.
It does not duplicate queue logic and does not execute privileged actions.
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
from urllib.parse import urlparse


CONTROL_URL = os.getenv("KOLIBRI_FACTORY_CONTROL_URL", "http://10.99.0.2:9101").rstrip("/")
AUTH_TOKEN_ENV = "KOLIBRI_CHATGPT_ACTION_TOKEN"
TIMEOUT = float(os.getenv("KOLIBRI_CHATGPT_ACTION_TIMEOUT", "5"))
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
)


def utc_ms() -> int:
    return int(time.time() * 1000)


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


def control_request(method: str, path: str, body: dict[str, Any] | None = None, timeout: float = TIMEOUT) -> tuple[int, dict[str, Any]]:
    url = f"{CONTROL_URL}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": "control_plane_http_error", "detail": raw[:300]}
        return exc.code, payload
    except Exception as exc:
        return 503, blocked("control_plane_unavailable", repair_task="repair_control_plane_api", detail=safe_error(exc))


def blocked(reason: str, *, repair_task: str, detail: str = "", task_id: str = "") -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason": reason,
        "task_id": task_id,
        "detail": detail,
        "repair_task": {"kind": repair_task},
        "next_action": "restore Control Plane reachability or request owner approval for the repair path",
    }


def approval_required(body: dict[str, Any], reason: str = "approval_required") -> dict[str, Any]:
    request_id = body.get("approval_id") or f"approval-{utc_ms()}-{uuid.uuid4().hex[:8]}"
    return {
        "status": "approval_required",
        "approval_id": request_id,
        "reason": reason,
        "requested_action": body.get("action") or body.get("kind") or "factory_action",
        "next_action": "owner must approve explicitly before any privileged execution",
    }


def contains_dangerous_action(body: dict[str, Any]) -> bool:
    text = json.dumps(body, ensure_ascii=False).lower()
    return any(marker in text for marker in DANGEROUS_ACTIONS)


def route(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    body = body or {}
    if path == "/v1/action/health" and method == "GET":
        status, control = control_request("GET", "/v1/health", timeout=2)
        return 200, {
            "status": "ok",
            "gateway": "kolibri-chatgpt-action",
            "auth_token_configured": token_configured(),
            "control_plane": "reachable" if status < 500 else "unreachable",
            "control_status": control.get("status") or control.get("error") or control.get("reason"),
        }
    if path == "/v1/factory/start" and method == "POST":
        if contains_dangerous_action(body):
            return 202, approval_required(body, "dangerous_action_requires_owner_approval")
        health_status, health = control_request("GET", "/v1/health", timeout=2)
        if health_status >= 500:
            return 503, blocked("factory_control_unreachable", repair_task="repair_control_plane_api", detail=health.get("detail", ""))
        return 202, {"status": "running", "factory_run_id": body.get("factory_run_id") or f"factory-{utc_ms()}-{uuid.uuid4().hex[:8]}", "mode": body.get("mode", "dry_run"), "control_plane": health, "next_action": "submit bounded tasks through /v1/tasks/submit"}
    if path == "/v1/director/tick" and method == "POST":
        if contains_dangerous_action(body):
            return 202, approval_required(body, "dangerous_action_requires_owner_approval")
        return 200, {"status": "completed", "tick_id": body.get("tick_id") or f"tick-{utc_ms()}-{uuid.uuid4().hex[:8]}", "actions": ["read_fleet_status", "read_queue_status", "report_blockers"], "next_action": "call /v1/fleet/status and /v1/queue/status"}
    if path == "/v1/fleet/status" and method == "GET":
        status, payload = control_request("GET", "/v1/fleet/nodes")
        if status == 404:
            status, payload = control_request("GET", "/v1/nodes")
        return status, payload
    if path == "/v1/queue/status" and method == "GET":
        status, payload = control_request("GET", "/v1/tasks/queue/diagnostics")
        if status == 404:
            status, payload = control_request("GET", "/v1/tasks")
        return status, payload
    if path == "/v1/tasks/submit" and method == "POST":
        if contains_dangerous_action(body):
            return 202, approval_required(body, "dangerous_action_requires_owner_approval")
        return control_request("POST", "/v1/agents/tasks", body)
    if path.startswith("/v1/tasks/") and path.endswith("/status") and method == "GET":
        task_id = path.split("/")[3]
        return control_request("GET", f"/v1/agents/status/{task_id}")
    if path.startswith("/v1/tasks/") and path.endswith("/artifacts") and method == "GET":
        task_id = path.split("/")[3]
        return control_request("GET", f"/v1/agents/artifacts/{task_id}")
    if path == "/v1/approvals/request" and method == "POST":
        return 202, approval_required(body)
    return 404, {"status": "blocked", "reason": "not_found", "path": path}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _serve(self, method: str) -> None:
        if not authorized(self.headers):
            write_json(self, 401, {"status": "blocked", "reason": "unauthorized"})
            return
        parsed = urlparse(self.path)
        try:
            body = read_body(self) if method == "POST" else {}
            status, payload = route(method, parsed.path.rstrip("/") or "/", body)
            write_json(self, status, payload)
        except Exception as exc:
            write_json(self, 500, {"status": "failed", "reason": "gateway_error", "detail": safe_error(exc)})

    def do_GET(self) -> None:
        self._serve("GET")

    def do_POST(self) -> None:
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
