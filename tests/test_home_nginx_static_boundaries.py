from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "ops/nginx/kolibriai-home.conf"


def _location_block(source: str, declaration: str) -> str:
    marker = f"location {declaration} {{"
    start = source.find(marker)
    assert start >= 0, f"missing nginx location: {declaration}"
    cursor = start + len(marker)
    depth = 1
    while cursor < len(source) and depth:
        if source[cursor] == "{":
            depth += 1
        elif source[cursor] == "}":
            depth -= 1
        cursor += 1
    assert depth == 0, f"unterminated nginx location: {declaration}"
    return source[start:cursor]


def test_hashed_assets_fail_closed_instead_of_returning_spa_html() -> None:
    source = CONFIG.read_text(encoding="utf-8")
    assets = _location_block(source, "^~ /assets/")

    assert "root /opt/kolibri-ai/current/frontend/dist;" in assets
    assert "try_files $uri =404;" in assets
    assert "/index.html" not in assets
    assert 'Cache-Control "public, max-age=31536000, immutable"' in assets
    assert "add_header X-Content-Type-Options nosniff always;" in assets


def test_public_root_assets_have_exact_non_spa_boundaries() -> None:
    source = CONFIG.read_text(encoding="utf-8")
    expected = {
        "= /kolibri-bird.png": "default_type image/png;",
        "= /sw.js": "default_type application/javascript;",
        "= /manifest.webmanifest": "default_type application/manifest+json;",
        "= /manifest.json": "default_type application/manifest+json;",
        "= /favicon.ico": "default_type image/x-icon;",
        "= /telegram-miniapp.html": "default_type text/html;",
        "= /index.html": "add_header Cache-Control \"no-cache\" always;",
    }

    for declaration, required_type_or_header in expected.items():
        block = _location_block(source, declaration)
        assert "root /opt/kolibri-ai/current/frontend/dist;" in block
        assert "try_files $uri =404;" in block
        assert "/index.html" not in block.replace("location = /index.html", "")
        assert required_type_or_header in block
        if "add_header Cache-Control" in block:
            assert "add_header X-Content-Type-Options nosniff always;" in block


def test_api_namespaces_cannot_fall_through_to_spa() -> None:
    source = CONFIG.read_text(encoding="utf-8")

    for exact in ("= /api", "= /v1"):
        block = _location_block(source, exact)
        assert "default_type application/json;" in block
        assert "return 404" in block
        assert "api_route_not_found" in block
        assert "/index.html" not in block

    for prefix in ("^~ /api/", "^~ /v1/"):
        block = _location_block(source, prefix)
        assert "proxy_pass http://127.0.0.1:8001;" in block
        assert "/index.html" not in block

    spa = _location_block(source, "/")
    assert "try_files $uri $uri/ /index.html;" in spa
