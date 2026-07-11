from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import execution_api


def _clear_inline_auth(monkeypatch) -> None:
    for name in ("KOLIBRI_API_KEY", "KOLIBRI_OWNER_API_TOKEN", "KOLIBRI_API_KEYS"):
        monkeypatch.delenv(name, raising=False)


def _client(tmp_path: Path) -> TestClient:
    execution_api.configure_execution_store(tmp_path / "execution.db")
    app = FastAPI()
    app.include_router(execution_api.router)
    return TestClient(app)


def test_owner_bearer_is_loaded_from_root_managed_file_without_cleartext_state(
    tmp_path, monkeypatch,
):
    token = "owner-file-test-token"
    token_file = tmp_path / "owner-api-token"
    token_file.write_text(token + "\n", encoding="utf-8")
    token_file.chmod(0o640)
    _clear_inline_auth(monkeypatch)
    monkeypatch.setenv("KOLIBRI_OWNER_API_TOKEN_FILE", str(token_file))
    execution_api.reload_execution_auth_from_environment()

    expected_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert execution_api._EXECUTION_KEY_HASHES == frozenset({expected_hash})
    assert token not in repr(execution_api._EXECUTION_KEY_HASHES)
    client = _client(tmp_path)
    assert client.get(
        "/v1/projects", headers={"Authorization": f"Bearer {token}"},
    ).status_code == 200
    assert client.get(
        "/v1/projects", headers={"Authorization": "Bearer wrong-token"},
    ).status_code == 401


def test_explicit_unsafe_owner_token_file_fails_closed_without_secret_echo(
    tmp_path, monkeypatch, capsys,
):
    token = "unsafe-owner-file-token"
    token_file = tmp_path / "owner-api-token"
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o644)
    _clear_inline_auth(monkeypatch)
    monkeypatch.setenv("KOLIBRI_OWNER_API_TOKEN_FILE", str(token_file))
    execution_api.reload_execution_auth_from_environment()

    response = _client(tmp_path).get(
        "/v1/projects", headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "execution_api_auth_token_file_invalid"
    assert token not in response.text
    captured = capsys.readouterr()
    assert token not in captured.out + captured.err


def test_owner_token_symlink_is_rejected(tmp_path, monkeypatch):
    real = tmp_path / "real-token"
    real.write_text("owner-symlink-token", encoding="utf-8")
    real.chmod(0o600)
    link = tmp_path / "owner-api-token"
    try:
        link.symlink_to(real)
    except OSError:
        return
    _clear_inline_auth(monkeypatch)
    monkeypatch.setenv("KOLIBRI_OWNER_API_TOKEN_FILE", str(link))
    execution_api.reload_execution_auth_from_environment()
    assert _client(tmp_path).get(
        "/v1/projects", headers={"Authorization": "Bearer owner-symlink-token"},
    ).status_code == 503


def test_home_backend_dropin_declares_owner_token_file_not_token_value():
    dropin = (ROOT / "ops/systemd/kolibri-backend-home-release.conf").read_text(
        encoding="utf-8"
    )
    assert "Environment=KOLIBRI_OWNER_API_TOKEN_FILE=/etc/kolibri/owner-api-token" in dropin
    assert "Environment=KOLIBRI_OWNER_API_TOKEN=" not in dropin
