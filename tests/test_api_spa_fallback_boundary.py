from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def load_backend_main(tmp_path: Path, monkeypatch):
    frontend = tmp_path / "frontend-dist"
    (frontend / "assets").mkdir(parents=True)
    (frontend / "index.html").write_text(
        "<!doctype html><html><body>SPA boundary sentinel</body></html>",
        encoding="utf-8",
    )
    monkeypatch.setenv("KOLIBRI_FRONTEND_DIST", str(frontend))
    monkeypatch.setenv("KOLIBRI_DATA_DIR", str(tmp_path / "kolibri-data"))
    monkeypatch.setenv(
        "KOLIBRI_EXECUTION_DB_PATH",
        str(tmp_path / "kolibri-data" / "execution.db"),
    )
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    for module_name in ("data_paths", "execution_api", "public_estimate_api", "public_responses_api", "tts"):
        sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(
        "backend_main_spa_boundary_contract",
        BACKEND / "main.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_unknown_api_paths_never_fall_through_to_spa(tmp_path, monkeypatch):
    module = load_backend_main(tmp_path, monkeypatch)
    client = TestClient(module.app)

    spa = client.get("/control")
    assert spa.status_code == 200
    assert "SPA boundary sentinel" in spa.text
    assert spa.headers["content-type"].startswith("text/html")

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.headers["content-type"].startswith("application/json")
    wrong_method = client.post("/api/health")
    assert wrong_method.status_code == 405
    assert wrong_method.headers["content-type"].startswith("application/json")
    assert "SPA boundary sentinel" not in wrong_method.text

    compatibility = client.get("/v1/kolibri/openai-compatibility")
    assert compatibility.status_code == 200
    assert compatibility.json()["routing_policy"]["wildcard_v1_proxy"] is False
    realtime = client.get("/v1/realtime")
    assert realtime.status_code == 501
    assert realtime.json()["error"]["code"] == "realtime_unavailable"

    for method, path in (
        ("GET", "/api/not-a-route"),
        ("POST", "/api/not-a-route"),
        ("GET", "/v1/not-a-route"),
        ("PATCH", "/v1/not-a-route"),
        ("GET", "/api"),
        ("GET", "/v1"),
    ):
        response = client.request(method, path)
        assert response.status_code == 404, (method, path, response.text)
        assert response.headers["content-type"].startswith("application/json")
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {"detail": "api_route_not_found"}
        assert "SPA boundary sentinel" not in response.text

    paths = module.app.openapi()["paths"]
    assert "/api/{full_path}" not in paths
    assert "/v1/{full_path}" not in paths
    assert "/v1/kolibri/openai-compatibility" in paths
    assert "/v1/responses/{response_id}/input_items" in paths
    assert "/v1/realtime" in paths
    assert not any(path.startswith("/v1/organization/") for path in paths)
