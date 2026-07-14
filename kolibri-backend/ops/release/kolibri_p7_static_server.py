#!/usr/bin/env python3
"""Minimal fail-closed static SPA server for the immutable P7 frontend.

The server deliberately has no directory listing and never turns a missing
asset into ``index.html``.  Only extensionless application routes receive the
SPA shell.  Nginx remains the public TLS boundary; this listener is loopback
only.
"""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path, PurePosixPath
import re
from urllib.parse import unquote, urlsplit


SAFE_RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
INTERNAL_SHELL_ROUTES = frozenset(
    {
        "agents",
        "app",
        "apps",
        "chat",
        "control",
        "documents",
        "estimates",
        "library",
        "login",
        "playground",
        "servers",
        "settings",
        "share",
    }
)


class StaticServerError(RuntimeError):
    """Raised before serving when the immutable frontend is invalid."""


def _request_path(raw: str) -> PurePosixPath:
    decoded = unquote(urlsplit(raw).path)
    candidate = PurePosixPath(decoded)
    if not decoded.startswith("/") or any(part in {"", ".", ".."} for part in candidate.parts[1:]):
        raise StaticServerError("invalid_request_path")
    return candidate


def _is_internal_shell_route(raw: str) -> bool:
    request_path = _request_path(raw)
    return len(request_path.parts) > 1 and request_path.parts[1] in INTERNAL_SHELL_ROUTES


def build_handler(root: Path, release_id: str):
    root = root.resolve(strict=True)
    if not root.is_dir() or not (root / "index.html").is_file():
        raise StaticServerError("frontend_dist_invalid")
    if not SAFE_RELEASE_ID.fullmatch(release_id):
        raise StaticServerError("release_id_invalid")

    class Handler(SimpleHTTPRequestHandler):
        server_version = "KolibriP7Static/1"

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, _format: str, *args) -> None:
            # Access logging is owned by nginx/OTel.  Avoid writing request
            # values to stderr from the privileged release runtime.
            return

        def end_headers(self) -> None:
            self.send_header("X-Kolibri-Release", release_id)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
            try:
                if _is_internal_shell_route(self.path):
                    self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
            except StaticServerError:
                # Invalid paths fail through the honest 404 target below. They
                # must never broaden the set of indexable application routes.
                self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
            super().end_headers()

        def _resolved_target(self) -> tuple[Path, bool]:
            request_path = _request_path(self.path)
            relative = Path(*request_path.parts[1:])
            target = (root / relative).resolve(strict=False)
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise StaticServerError("request_path_escape") from exc
            if target.is_file():
                return target, False
            # Extensionless paths are client-side application routes.  Missing
            # hashed assets, icons, source maps and API-looking paths remain
            # honest 404s rather than receiving HTML with the wrong MIME type.
            spa_route = (
                request_path == PurePosixPath("/")
                or (
                    not request_path.suffix
                    and not str(request_path).startswith(("/api/", "/v1/", "/ws/", "/assets/"))
                )
            )
            return (root / "index.html", True) if spa_route else (target, False)

        def translate_path(self, path: str) -> str:
            try:
                target, _spa = self._resolved_target()
            except StaticServerError:
                return str(root / ".invalid-request")
            return str(target)

        def list_directory(self, _path: str):
            self.send_error(HTTPStatus.NOT_FOUND)
            return None

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=15194)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.host not in {"127.0.0.1", "::1"}:
        raise SystemExit("frontend_listener_must_be_loopback")
    if not 1 <= args.port <= 65535:
        raise SystemExit("frontend_port_invalid")
    root = Path(args.root)
    handler = build_handler(root, args.release_id)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    server.daemon_threads = True
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    os.umask(0o027)
    raise SystemExit(main())
