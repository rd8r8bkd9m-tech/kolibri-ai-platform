#!/usr/bin/env python3
"""Kolibri Fleet API — HTTP API для классификации флота.

Запуск: python3 ops/fleet_api.py --port 9102
Доступ: http://192.168.88.210:9102/v1/fleet/classification
"""

from __future__ import annotations

import json
import sys
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(__file__))
from fleet_classification import build_fleet_classification, FleetClassification

fleet: FleetClassification | None = None


class FleetHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global fleet
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/v1/fleet/classification":
            self._json_response(fleet.to_dict())
        elif path == "/v1/fleet/servers":
            self._json_response([s.to_dict() for s in fleet.servers.values()])
        elif path.startswith("/v1/fleet/servers/"):
            server_id = path.split("/")[-1]
            if server_id in fleet.servers:
                self._json_response(fleet.servers[server_id].to_dict())
            else:
                self._json_response({"error": f"Server {server_id} not found"}, 404)
        elif path == "/v1/fleet/subnets":
            self._json_response([s.to_dict() for s in fleet.subnets.values()])
        elif path == "/v1/health":
            self._json_response({"status": "ok", "servers": len(fleet.servers), "subnets": len(fleet.subnets)})
        else:
            self._json_response({"error": "Not found", "endpoints": [
                "/v1/fleet/classification",
                "/v1/fleet/servers",
                "/v1/fleet/servers/{id}",
                "/v1/fleet/subnets",
                "/v1/health",
            ]}, 404)

    def _json_response(self, data: dict | list, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Suppress logs


def main():
    global fleet
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9102
    fleet = build_fleet_classification()
    server = ThreadingHTTPServer(("0.0.0.0", port), FleetHandler)
    print(f"Fleet API listening on http://0.0.0.0:{port}")
    print(f"  GET /v1/fleet/classification — полная классификация")
    print(f"  GET /v1/fleet/servers — все серверы")
    print(f"  GET /v1/fleet/servers/{{id}} — один сервер")
    print(f"  GET /v1/fleet/subnets — подсети")
    print(f"  GET /v1/health — здоровье")
    server.serve_forever()


if __name__ == "__main__":
    main()
