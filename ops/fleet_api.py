#!/usr/bin/env python3
"""Kolibri Fleet API — HTTP API для классификации флота и деплоя.

Запуск: python3 ops/fleet_api.py --port 9102
Доступ: http://192.168.88.210:9102/v1/fleet/classification
"""

from __future__ import annotations

import json
import subprocess
import sys
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(__file__))
from fleet_classification import build_fleet_classification, FleetClassification

fleet: FleetClassification | None = None
deploy_results: dict[str, dict] = {}


SSH_KEY = "/home/ladik/.ssh/id_ed25519"
DEPLOY_BASE = "/opt/kolibri-ai-platform"
LOCAL_REPO = "/Users/kolibri/Documents/Codex/kolibri-ai-platform"


def ssh_exec(host: str, command: str, timeout: int = 30) -> dict:
    try:
        result = subprocess.run(
            ["ssh", "-i", SSH_KEY, "-o", "ConnectTimeout=10", "-o", "BatchMode=yes", host, command],
            capture_output=True, text=True, timeout=timeout
        )
        return {"status": "ok" if result.returncode == 0 else "error", "output": result.stdout.strip(), "error": result.stderr.strip()}
    except Exception as e:
        return {"status": "error", "output": "", "error": str(e)}


def deploy_to_server(server_id: str, ssh_alias: str, files: list[str]):
    global deploy_results
    deploy_results[server_id] = {"status": "deploying", "files": [], "errors": []}

    for f in files:
        local_path = f"{DEPLOY_BASE}/{f}"
        remote_dir = f"{DEPLOY_BASE}/{os.path.dirname(f)}"
        ssh_exec(ssh_alias, f"mkdir -p {remote_dir}")
        r = subprocess.run(
            ["scp", "-i", SSH_KEY, "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no", local_path, f"{ssh_alias}:{DEPLOY_BASE}/{f}"],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0:
            deploy_results[server_id]["files"].append(f)
        else:
            deploy_results[server_id]["errors"].append(f"{f}: {r.stderr[:100]}")

    deploy_results[server_id]["status"] = "ok" if not deploy_results[server_id]["errors"] else "partial"


def deploy_to_server_by_ip(server_id: str, ip: str, files: list[str]):
    global deploy_results
    deploy_results[server_id] = {"status": "deploying", "files": [], "errors": []}

    for f in files:
        local_path = f"{DEPLOY_BASE}/{f}"
        ssh_exec(f"root@{ip}", f"mkdir -p {DEPLOY_BASE}/{os.path.dirname(f)}")
        r = subprocess.run(
            ["scp", "-i", SSH_KEY, "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no", local_path, f"root@{ip}:{DEPLOY_BASE}/{f}"],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0:
            deploy_results[server_id]["files"].append(f)
        else:
            deploy_results[server_id]["errors"].append(f"{f}: {r.stderr[:100]}")

    deploy_results[server_id]["status"] = "ok" if not deploy_results[server_id]["errors"] else "partial"


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
        elif path == "/v1/fleet/deploy/status":
            self._json_response(deploy_results)
        elif path == "/v1/health":
            self._json_response({"status": "ok", "servers": len(fleet.servers), "subnets": len(fleet.subnets)})
        else:
            self._json_response({"error": "Not found", "endpoints": [
                "/v1/fleet/classification", "/v1/fleet/servers",
                "/v1/fleet/servers/{id}", "/v1/fleet/subnets",
                "/v1/fleet/deploy", "/v1/fleet/deploy/status", "/v1/health",
            ]}, 404)

    def do_POST(self):
        global fleet, deploy_results
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}

        if path == "/v1/fleet/deploy":
            files = body.get("files", [
                "ops/fleet_classification.py",
                "ops/fleet_api.py",
                "ops/mimo_client.py",
            ])
            servers = body.get("servers", "all")

            if servers == "all":
                target_servers = [(s.node_id, s.internal_ip or s.external_ip) for s in fleet.servers.values() if s.internal_ip or s.external_ip]
            else:
                target_servers = [(s, fleet.servers[s].internal_ip or fleet.servers[s].external_ip) for s in servers if s in fleet.servers]

            deploy_results = {}
            threads = []
            for server_id, ip in target_servers:
                if ip:
                    t = threading.Thread(target=deploy_to_server_by_ip, args=(server_id, ip, files))
                    threads.append(t)
                    t.start()

            for t in threads:
                t.join(timeout=120)

            ok_count = sum(1 for r in deploy_results.values() if r["status"] == "ok")
            self._json_response({"deployed": ok_count, "total": len(target_servers), "results": deploy_results})
        else:
            self._json_response({"error": "Not found"}, 404)

    def _json_response(self, data: dict | list, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def main():
    global fleet
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9102
    fleet = build_fleet_classification()
    server = ThreadingHTTPServer(("0.0.0.0", port), FleetHandler)
    print(f"Fleet API listening on http://0.0.0.0:{port}")
    print(f"  GET  /v1/fleet/classification — классификация")
    print(f"  GET  /v1/fleet/servers — серверы")
    print(f"  POST /v1/fleet/deploy — деплой на серверы")
    print(f"  GET  /v1/fleet/deploy/status — статус деплоя")
    print(f"  GET  /v1/health — здоровье")
    server.serve_forever()


if __name__ == "__main__":
    main()
