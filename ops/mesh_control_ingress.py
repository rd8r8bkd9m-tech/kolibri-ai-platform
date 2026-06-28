#!/usr/bin/env python3
"""Mesh ingress for Kolibri Control Plane.

The public VPS workers do not all have a direct 10.99.0.0/24 route yet. This
small reverse proxy lets them use the Home mesh API as the control transport
while keeping the accepted paths narrow and source IP allowlisted.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


DEFAULT_LISTEN = os.environ.get("KOLIBRI_MESH_CONTROL_LISTEN", "0.0.0.0:9181")
DEFAULT_TARGET = os.environ.get("KOLIBRI_FACTORY_CONTROL_URL", "http://10.99.0.2:9101").rstrip("/")
DEFAULT_ALLOWED = "127.0.0.0/8,10.99.0.0/24"
ALLOWED_CIDRS = os.environ.get("KOLIBRI_MESH_CONTROL_ALLOWED_CIDRS", DEFAULT_ALLOWED)
MAX_BODY = int(os.environ.get("KOLIBRI_MESH_CONTROL_MAX_BODY", str(1024 * 1024)))


def parse_networks(value: str) -> list[ipaddress._BaseNetwork]:
    networks: list[ipaddress._BaseNetwork] = []
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        networks.append(ipaddress.ip_network(item, strict=False))
    return networks


def path_allowed(method: str, path: str) -> bool:
    if method == "GET" and path in {"/health", "/v1/health", "/v1/filesystem"}:
        return True
    if method == "GET" and path == "/v1/nodes":
        return True
    if method == "POST" and path in {"/v1/nodes/register", "/v1/tasks/lease", "/v1/tasks"}:
        return True
    if method == "POST" and path.startswith("/v1/nodes/") and path.endswith("/heartbeat"):
        return True
    if method == "POST" and path.startswith("/v1/tasks/") and (
        path.endswith("/heartbeat") or path.endswith("/complete") or path.endswith("/fail")
    ):
        return True
    return False


class IngressHandler(BaseHTTPRequestHandler):
    server_version = "KolibriMeshControlIngress/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    @property
    def target(self) -> str:
        return self.server.target  # type: ignore[attr-defined]

    @property
    def allowed_networks(self) -> list[ipaddress._BaseNetwork]:
        return self.server.allowed_networks  # type: ignore[attr-defined]

    def client_allowed(self) -> bool:
        try:
            ip = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return False
        return any(ip in network for network in self.allowed_networks)

    def read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or "0")
        if length > MAX_BODY:
            raise ValueError("request body too large")
        if not length:
            return b""
        return self.rfile.read(length)

    def proxy(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if not self.client_allowed():
            self.respond(403, b'{"error":"source_not_allowed"}', "application/json")
            return
        if not path_allowed(self.command, path):
            self.respond(404, b'{"error":"path_not_allowed"}', "application/json")
            return
        try:
            body = self.read_body() if self.command in {"POST", "PUT", "PATCH"} else None
        except ValueError as exc:
            self.respond(413, str(exc).encode("utf-8"), "text/plain")
            return

        query = f"?{parsed.query}" if parsed.query else ""
        target_url = f"{self.target}{path}{query}"
        headers = {"Content-Type": self.headers.get("Content-Type", "application/json")}
        req = urllib.request.Request(target_url, data=body, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=30) as upstream:
                payload = upstream.read()
                content_type = upstream.headers.get("Content-Type", "application/json")
                self.respond(upstream.status, payload, content_type)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            self.respond(exc.code, payload, exc.headers.get("Content-Type", "application/json"))
        except Exception as exc:
            self.respond(502, f'{{"error":"upstream_unavailable","detail":"{type(exc).__name__}"}}'.encode(), "application/json")

    def respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        self.proxy()

    def do_POST(self) -> None:  # noqa: N802
        self.proxy()


class IngressServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler: type[IngressHandler], target: str, allowed: str):
        super().__init__(server_address, handler)
        self.target = target.rstrip("/")
        self.allowed_networks = parse_networks(allowed)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Expose narrow Control Plane API through Home mesh ingress.")
    parser.add_argument("--listen", default=DEFAULT_LISTEN)
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--allowed-cidrs", default=ALLOWED_CIDRS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    host, port_raw = args.listen.rsplit(":", 1)
    server = IngressServer((host, int(port_raw)), IngressHandler, args.target, args.allowed_cidrs)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
