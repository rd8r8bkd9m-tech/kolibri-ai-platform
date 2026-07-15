#!/usr/bin/env python3
"""Node-local HTTP relay to the single logical Kolibri Control Plane."""
from __future__ import annotations

import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TARGET = os.environ.get("KOLIBRI_CONTROL_PLANE_TARGET", "http://10.99.0.2:9101").rstrip("/")
BIND = os.environ.get("KOLIBRI_CONTROL_PLANE_RELAY_BIND", "127.0.0.1")
PORT = int(os.environ.get("KOLIBRI_CONTROL_PLANE_RELAY_PORT", "9101"))


class Handler(BaseHTTPRequestHandler):
    def _relay(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(size) if size else None
        headers = {"Content-Type": self.headers.get("Content-Type", "application/json")}
        request = urllib.request.Request(f"{TARGET}{self.path}", data=data, method=self.command, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as upstream:
                body = upstream.read()
                status = upstream.status
                content_type = upstream.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as exc:
            body = exc.read()
            status = exc.code
            content_type = exc.headers.get("Content-Type", "application/json")
        except Exception as exc:
            body = ('{"error":"control_plane_unreachable","detail":"%s"}' % type(exc).__name__).encode()
            status = 503
            content_type = "application/json"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = _relay
    do_POST = _relay
    do_PUT = _relay
    do_PATCH = _relay
    do_DELETE = _relay

    def log_message(self, *_args) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
