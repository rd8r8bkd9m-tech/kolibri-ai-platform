from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KOLIBRI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("KOLIBRI_DB_PATH", str(tmp_path / "data" / "kolibri.db"))
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path / "data" / "artifacts"))
    monkeypatch.setenv("KOLIBRI_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("KOLIBRI_NODE_JOIN_TOKEN", "node-secret")
    monkeypatch.setenv("KOLIBRI_OWNER_ACCESS_TOKEN", "owner-secret")
    monkeypatch.setenv("KOLIBRI_OPERATOR_ACCESS_TOKEN", "operator-secret")
    monkeypatch.setenv("KOLIBRI_DEVELOPER_ACCESS_TOKEN", "developer-secret")
    monkeypatch.setenv("KOLIBRI_EXPOSE_SESSION_TOKEN", "1")
    test_api_key = "sk-" + "kolibri-" + "test-developer-key"
    monkeypatch.setenv(
        "KOLIBRI_API_KEYS_JSON",
        json.dumps({test_api_key: {"role": "developer", "name": "test-suite"}}),
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    from kolibri_v2.app import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def bootstrap(client: TestClient, role: str = "client") -> tuple[str, str]:
    role_tokens = {"owner": "owner-secret", "operator": "operator-secret", "developer": "developer-secret"}
    headers = {"X-Kolibri-Access-Token": role_tokens[role]} if role in role_tokens else {}
    response = client.post("/v1/shell/bootstrap", headers=headers, json={"role": role})
    assert response.status_code == 200, response.text
    payload = response.json()
    return payload["session"]["token"], payload["active_project"]["id"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
