import importlib.util
from pathlib import Path
import sys
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]


def load_main():
    backend_dir = ROOT / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    spec = importlib.util.spec_from_file_location("kolibri_backend_main", ROOT / "backend" / "main.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_resolve_frontend_path_prefers_repo_dist_when_opt_is_missing(monkeypatch):
    monkeypatch.delenv("KOLIBRI_FRONTEND_DIST", raising=False)
    module = load_main()
    resolved = module.resolve_frontend_path()
    assert resolved is not None
    assert resolved == ROOT / "frontend" / "dist"
    assert resolved.exists()


def test_resolve_frontend_path_honors_explicit_env(monkeypatch, tmp_path):
    custom = tmp_path / "custom-dist"
    custom.mkdir()
    (custom / "assets").mkdir()
    monkeypatch.setenv("KOLIBRI_FRONTEND_DIST", str(custom))
    module = load_main()
    assert module.resolve_frontend_path() == custom


def test_assets_are_served_even_with_proxy_route_present(monkeypatch, tmp_path):
    custom = tmp_path / "custom-dist"
    assets = custom / "assets"
    assets.mkdir(parents=True)
    (custom / "index.html").write_text("<!doctype html><html><body>ok</body></html>", encoding="utf-8")
    (assets / "miniapp.js").write_text("console.log('ok')", encoding="utf-8")
    monkeypatch.setenv("KOLIBRI_FRONTEND_DIST", str(custom))
    module = load_main()
    client = TestClient(module.app)
    response = client.get("/assets/miniapp.js")
    assert response.status_code == 200
    assert "console.log('ok')" in response.text
