from __future__ import annotations

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def test_factory_status_outage_is_public_panel_json_200(monkeypatch):
    import main

    async def fail_fetch():
        raise RuntimeError("control plane offline")

    monkeypatch.setattr(main, "fetch_factory_status", fail_fetch)
    client = TestClient(main.app)

    response = client.get("/api/factory/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["source"] == "control-plane"
    assert body["public_panel"]["status_contract"] == "ok"
    assert body["control_plane"]["reason"] == "control_plane_api_unreachable"
    assert body["node_freshness"] == {"fresh": 0, "degraded": 0, "stale": 0, "online": 0, "total": 0}


@pytest.mark.parametrize("path", ["/factory/status", "/cluster/status", "/api/cluster/status"])
def test_factory_status_aliases_return_same_contract(monkeypatch, path):
    import main

    async def status_payload():
        return {"status": "online", "source": "test", "nodes": {}, "node_list": []}

    monkeypatch.setattr(main, "fetch_factory_status", status_payload)
    client = TestClient(main.app)

    response = client.get(path)

    assert response.status_code == 200
    assert response.json()["status"] == "online"


def test_nginx_has_exact_factory_panel_routes_before_generic_api_proxy():
    nginx = (ROOT / "infra" / "network" / "nginx.conf").read_text(encoding="utf-8")

    exact_factory = nginx.index("location = /api/factory/status")
    exact_alias = nginx.index("location = /factory/status")
    exact_cluster = nginx.index("location = /cluster/status")
    generic_api = nginx.index("location /api/")

    assert exact_factory < generic_api
    assert exact_alias < generic_api
    assert exact_cluster < generic_api
    assert "proxy_pass http://127.0.0.1:8000/api/factory/status;" in nginx
    assert "proxy_pass http://127.0.0.1:8000/cluster/status;" in nginx


def test_deploy_main_installs_nginx_with_rollback_backup():
    deploy = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")

    assert "infra/network/nginx.conf kolibri-main:/tmp/kolibri-ai-nginx.conf" in deploy
    assert "/opt/kolibri-ai/rollback/kolibri-ai.nginx.\\$ts.conf" in deploy
    assert "install -m 0644 /tmp/kolibri-ai-nginx.conf /etc/nginx/sites-available/kolibri-ai" in deploy
    assert "nginx -t && systemctl reload nginx" in deploy
