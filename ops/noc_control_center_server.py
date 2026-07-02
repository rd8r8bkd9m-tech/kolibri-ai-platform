#!/usr/bin/env python3
"""Kolibri AI Control Center — Home NOC server.

Serves the NOC wallboard dashboard on port 9191 and exposes /api/snapshot
for health/status/counts. Polls factory_control.py at KOLIBRI_FACTORY_CONTROL_URL.

Port 9191 is hardcoded; the client portal (8180) is NOT served by this process.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

NOC_PORT = int(os.environ.get("KOLIBRI_NOC_PORT", "9191"))
FACTORY_CONTROL_URL = os.environ.get(
    "KOLIBRI_FACTORY_CONTROL_URL", "http://10.99.0.2:9101"
)
WALLBOARD_PATH = Path(__file__).parent / "noc_wallboard.html"
CLIENT_PORTAL_FORBIDDEN = 8180

_snapshot_cache: dict = {}
_snapshot_ts: float = 0.0
SNAPSHOT_TTL = float(os.environ.get("KOLIBRI_NOC_SNAPSHOT_TTL", "5"))


def _fetch_factory(path: str, timeout: float = 3.0) -> dict | list | None:
    url = f"{FACTORY_CONTROL_URL}{path}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def build_snapshot() -> dict:
    global _snapshot_cache, _snapshot_ts
    now = time.time()
    if _snapshot_cache and (now - _snapshot_ts) < SNAPSHOT_TTL:
        return _snapshot_cache

    health = _fetch_factory("/v1/health")
    nodes_raw = _fetch_factory("/v1/nodes")
    tasks_raw = _fetch_factory("/v1/tasks?compact=1&summary=1")

    nodes = nodes_raw if isinstance(nodes_raw, list) else []
    tasks = tasks_raw if isinstance(tasks_raw, list) else []

    node_states: dict[str, int] = {}
    for n in nodes:
        state = n.get("state", "unknown")
        node_states[state] = node_states.get(state, 0) + 1

    task_states: dict[str, int] = {}
    for t in tasks:
        state = t.get("state", "unknown")
        task_states[state] = task_states.get(state, 0) + 1

    snapshot = {
        "ts": int(now),
        "factory_control_url": FACTORY_CONTROL_URL,
        "health": health,
        "nodes_total": len(nodes),
        "nodes_by_state": node_states,
        "tasks_total": len(tasks),
        "tasks_by_state": task_states,
        "nodes": nodes[:50],
        "tasks": tasks[:100],
    }
    _snapshot_cache = snapshot
    _snapshot_ts = now
    return snapshot


class NOCRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path == "/api/snapshot":
            data = json.dumps(build_snapshot()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
            return

        if self.path == "/api/health":
            data = json.dumps({"status": "ok", "port": NOC_PORT}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if self.path == "/" or self.path == "/index.html":
            if WALLBOARD_PATH.exists():
                html = WALLBOARD_PATH.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            else:
                self.send_error(404, "Wallboard not found")
            return

        self.send_error(404)


def main():
    server = ThreadingHTTPServer(("0.0.0.0", NOC_PORT), NOCRequestHandler)
    print(f"NOC Control Center listening on http://0.0.0.0:{NOC_PORT}")
    print(f"Factory control URL: {FACTORY_CONTROL_URL}")
    print(f"Client portal (8180) is NOT served here")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down NOC server")
        server.shutdown()


if __name__ == "__main__":
    main()
