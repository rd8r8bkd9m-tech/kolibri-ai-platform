from __future__ import annotations

import importlib.util
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import urllib.error
import urllib.request

import pytest


SCRIPT = Path(__file__).parents[1] / "kolibri_p7_static_server.py"
SPEC = importlib.util.spec_from_file_location("kolibri_p7_static_server", SCRIPT)
assert SPEC and SPEC.loader
static = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = static
SPEC.loader.exec_module(static)


def _request(url: str):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            # HTTP header names are case-insensitive.  Keep HTTPMessage rather
            # than converting it to a case-sensitive dict (Python 3.14 emits
            # ``Content-type`` from SimpleHTTPRequestHandler).
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def test_static_server_spa_asset_404_and_release_identity(tmp_path: Path):
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html>kolibri-p7-test</html>")
    (root / "assets" / "app.js").write_text("console.log('ok')")
    (root / "robots.txt").write_text("User-agent: *\nAllow: /\nDisallow: /app\n")
    handler = static.build_handler(root, "kolibri-p7-test")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, headers, body = _request(base + "/app?project=one")
        assert status == 200
        assert headers["X-Kolibri-Release"] == "kolibri-p7-test"
        assert headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"
        assert b"kolibri-p7-test" in body

        status, headers, body = _request(base + "/")
        assert status == 200
        assert "X-Robots-Tag" not in headers
        assert b"kolibri-p7-test" in body

        status, headers, body = _request(base + "/docs")
        assert status == 200
        assert "X-Robots-Tag" not in headers
        assert b"kolibri-p7-test" in body

        status, headers, body = _request(base + "/chat/project-1")
        assert status == 200
        assert headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"
        assert b"kolibri-p7-test" in body

        status, headers, body = _request(base + "/robots.txt")
        assert status == 200
        assert headers["Content-Type"].startswith("text/plain")
        assert body == b"User-agent: *\nAllow: /\nDisallow: /app\n"

        status, headers, body = _request(base + "/assets/app.js")
        assert status == 200
        assert headers["X-Kolibri-Release"] == "kolibri-p7-test"
        assert body == b"console.log('ok')"

        status, headers, body = _request(base + "/assets/missing-C5zm.js")
        assert status == 404
        assert headers["X-Kolibri-Release"] == "kolibri-p7-test"
        assert b"kolibri-p7-test" not in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_canary_is_confined_to_release_prefix(tmp_path: Path):
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html>isolated-canary-shell</html>")
    (root / "assets" / "app-C5zm.js").write_text("console.log('canary')")
    release_id = "kolibri-live-reasoning-20260714-p7"
    prefix = f"/__canary/{release_id}/"
    handler = static.build_handler(root, release_id, prefix)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, headers, body = _request(base + prefix)
        assert status == 200
        assert headers["X-Kolibri-Release"] == release_id
        assert headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"
        assert b"isolated-canary-shell" in body

        status, headers, body = _request(base + prefix + "app?project=one")
        assert status == 200
        assert headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"
        assert b"isolated-canary-shell" in body

        status, headers, body = _request(base + prefix + "assets/app-C5zm.js")
        assert status == 200
        assert headers["Content-Type"].startswith(("text/javascript", "application/javascript"))
        assert body == b"console.log('canary')"

        status, headers, body = _request(base + prefix + "assets/missing-C5zm.js")
        assert status == 404
        assert b"isolated-canary-shell" not in body

        for outside_path in (
            "/",
            "/app",
            "/assets/app-C5zm.js",
            "/__canary/a-different-release/",
            prefix + "api/missing",
            prefix + "v1/responses",
            prefix + "assets",
            prefix + "%2e%2e/index.html",
        ):
            status, headers, body = _request(base + outside_path)
            assert status == 404, outside_path
            assert headers["X-Kolibri-Release"] == release_id
            assert b"isolated-canary-shell" not in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize(
    "base_path",
    (
        "relative",
        "/canary/kolibri-p7-test/",
        "/__canary/other-release/",
        "/__canary/kolibri-p7-test",
        "/__canary/kolibri-p7-test//",
    ),
)
def test_canary_base_path_is_exact_and_release_bound(tmp_path: Path, base_path: str):
    root = tmp_path / "dist"
    root.mkdir()
    (root / "index.html").write_text("<html>candidate</html>")

    with pytest.raises(static.StaticServerError, match="base_path_invalid"):
        static.build_handler(root, "kolibri-p7-test", base_path)


def test_parser_accepts_explicit_canary_base_path():
    args = static.build_parser().parse_args(
        [
            "--root",
            "/tmp/dist",
            "--release-id",
            "candidate-1",
            "--base-path",
            "/__canary/candidate-1/",
        ]
    )
    assert args.base_path == "/__canary/candidate-1/"
