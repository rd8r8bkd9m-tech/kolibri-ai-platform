#!/usr/bin/env python3
"""Deprecated read-only Fleet API compatibility facade.

This process does not own membership and cannot deploy over SSH.  Every read
is rebuilt from canonical Home Control Plane registration.  Mutations are
explicitly retired in favour of signed, fenced Factory release tasks.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(__file__))

from fleet_classification import build_fleet_classification  # noqa: E402


class FleetHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path.rstrip("/")
        try:
            fleet = build_fleet_classification()
        except Exception as exc:
            self._json_response(
                {
                    "status": "degraded",
                    "source": "home_mesh_manifest_canonical_membership",
                    "error": type(exc).__name__,
                },
                503,
            )
            return

        if path == "/v1/fleet/classification":
            self._json_response(fleet.to_dict())
        elif path == "/v1/fleet/servers":
            self._json_response([server.to_dict() for server in fleet.servers.values()])
        elif path.startswith("/v1/fleet/servers/"):
            server_id = path.rsplit("/", 1)[-1]
            server = fleet.servers.get(server_id)
            self._json_response(
                server.to_dict() if server else {"error": "node_not_registered"},
                200 if server else 404,
            )
        elif path == "/v1/fleet/subnets":
            self._json_response([subnet.to_dict() for subnet in fleet.subnets.values()])
        elif path == "/v1/health":
            self._json_response(
                {
                    "status": "ok",
                    "mode": "read_only_compatibility",
                    "source": "home_mesh_manifest_canonical_membership",
                    "servers": len(fleet.servers),
                }
            )
        else:
            self._json_response({"error": "not_found"}, 404)

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path.rstrip("/")
        if path in {"/v1/fleet/deploy", "/v1/fleet/register"}:
            self._json_response(
                {
                    "error": "legacy_fleet_mutation_retired",
                    "authority": "home_control_plane",
                    "next_action": "submit an owner-approved signed release through Factory API",
                },
                410,
            )
            return
        self._json_response({"error": "not_found"}, 404)

    def _json_response(self, data: dict | list, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def main() -> None:
    host = os.environ.get("KOLIBRI_FLEET_COMPAT_BIND", "127.0.0.1")
    port = int(os.environ.get("KOLIBRI_FLEET_COMPAT_PORT", "9102"))
    server = ThreadingHTTPServer((host, port), FleetHandler)
    print(f"read-only Fleet compatibility facade on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
