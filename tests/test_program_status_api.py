from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import execution_api
import program_status_api


def _status(*, as_of: datetime | None = None, overall_status: str = "in_progress") -> dict:
    timestamp = (as_of or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "kolibri.program-status.v1",
        "program_id": "kolibri-ai-os-home-first",
        "as_of": timestamp,
        "source_commit": "a" * 40,
        "overall_status": overall_status,
        "summary": {
            "acceptance_gate_progress": {
                "completed": 2,
                "in_progress": 3,
                "blocked": 3,
                "not_started": 3,
                "total": 11,
                "completed_ratio": 0.1818,
                "interpretation": "equal gate-count ratio",
            }
        },
        "evidence": [{
            "id": "evidence:one",
            "kind": "test",
            "status": "verified",
            "reference": "fixture",
            "uri": None,
            "observed_at": timestamp,
        }],
        "gates": [{
            "gate": 0,
            "id": "gate-0",
            "name": "Evidence baseline",
            "status": "completed",
            "evidence_ids": ["evidence:one"],
            "blockers": [],
            "next_action": "record the next checkpoint",
            "updated_at": timestamp,
        }],
    }


def _client(monkeypatch, tmp_path: Path, payload: dict | str | None = None) -> TestClient:
    path = tmp_path / "program-status.json"
    if isinstance(payload, dict):
        path.write_text(json.dumps(payload), encoding="utf-8")
    elif isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    monkeypatch.setenv(program_status_api.PROGRAM_STATUS_PATH_ENV, str(path))
    monkeypatch.setenv(program_status_api.PROGRAM_STATUS_MAX_AGE_ENV, "900")
    execution_api.configure_execution_auth(["owner-test-token"])
    app = FastAPI()
    app.include_router(program_status_api.router)
    return TestClient(app)


def _owner_headers(**extra: str) -> dict[str, str]:
    return {"Authorization": "Bearer owner-test-token", **extra}


def test_program_status_is_owner_only_and_never_uses_public_session(tmp_path, monkeypatch):
    old_hashes = execution_api._EXECUTION_KEY_HASHES
    old_error = execution_api._EXECUTION_AUTH_CONFIGURATION_ERROR
    try:
        client = _client(monkeypatch, tmp_path, _status())
        response = client.get("/v1/program/status")
        assert response.status_code == 401
        assert response.json()["detail"] == "execution_api_auth_required"
    finally:
        execution_api._EXECUTION_KEY_HASHES = old_hashes
        execution_api._EXECUTION_AUTH_CONFIGURATION_ERROR = old_error


def test_program_status_returns_source_bound_partial_projection_and_etag(tmp_path, monkeypatch):
    old_hashes = execution_api._EXECUTION_KEY_HASHES
    old_error = execution_api._EXECUTION_AUTH_CONFIGURATION_ERROR
    try:
        client = _client(monkeypatch, tmp_path, _status())
        response = client.get("/v1/program/status", headers=_owner_headers())
        assert response.status_code == 200
        payload = response.json()
        assert payload["schema_version"] == "kolibri.wallboard.program-status.v1"
        assert payload["availability"] == "partial"
        assert payload["source_freshness"] == "live"
        assert payload["source"] == "program-ledger/home"
        assert payload["gate_progress"]["completed"] == 2
        assert payload["gate_progress"]["total"] == 11
        assert payload["source_sha256"].startswith("sha256:")
        assert response.headers["cache-control"] == "no-store"
        etag = response.headers["etag"]
        cached = client.get(
            "/v1/program/status",
            headers=_owner_headers(**{"If-None-Match": etag}),
        )
        assert cached.status_code == 304
        assert cached.content == b""
    finally:
        execution_api._EXECUTION_KEY_HASHES = old_hashes
        execution_api._EXECUTION_AUTH_CONFIGURATION_ERROR = old_error


def test_program_status_marks_old_source_stale_without_zero_fallback(tmp_path, monkeypatch):
    old_hashes = execution_api._EXECUTION_KEY_HASHES
    old_error = execution_api._EXECUTION_AUTH_CONFIGURATION_ERROR
    try:
        client = _client(
            monkeypatch,
            tmp_path,
            _status(as_of=datetime.now(timezone.utc) - timedelta(hours=2)),
        )
        monkeypatch.setenv(program_status_api.PROGRAM_STATUS_MAX_AGE_ENV, "60")
        response = client.get("/v1/program/status", headers=_owner_headers())
        assert response.status_code == 200
        payload = response.json()
        assert payload["availability"] == "stale"
        assert payload["source_freshness"] == "stale"
        assert payload["age_seconds"] >= 7_199
    finally:
        execution_api._EXECUTION_KEY_HASHES = old_hashes
        execution_api._EXECUTION_AUTH_CONFIGURATION_ERROR = old_error


def test_program_status_missing_or_malformed_is_explicitly_unavailable(tmp_path, monkeypatch):
    old_hashes = execution_api._EXECUTION_KEY_HASHES
    old_error = execution_api._EXECUTION_AUTH_CONFIGURATION_ERROR
    try:
        missing = _client(monkeypatch, tmp_path)
        response = missing.get("/v1/program/status", headers=_owner_headers())
        assert response.status_code == 503
        assert response.json() == {
            "schema_version": "kolibri.wallboard.program-status.v1",
            "availability": "unavailable",
            "source_freshness": "unavailable",
            "source": "program-ledger/home",
            "reason": "program_status_source_unavailable",
        }

        malformed = _client(monkeypatch, tmp_path, "not-json")
        response = malformed.get("/v1/program/status", headers=_owner_headers())
        assert response.status_code == 503
        assert response.json()["availability"] == "unavailable"
        assert response.json()["reason"] == "program_status_source_invalid"
        assert "gate_progress" not in response.json()
    finally:
        execution_api._EXECUTION_KEY_HASHES = old_hashes
        execution_api._EXECUTION_AUTH_CONFIGURATION_ERROR = old_error


def test_program_status_rejects_secret_bearing_ledger(tmp_path, monkeypatch):
    old_hashes = execution_api._EXECUTION_KEY_HASHES
    old_error = execution_api._EXECUTION_AUTH_CONFIGURATION_ERROR
    try:
        payload = _status()
        payload["summary"]["provider"] = {"api_key": "must-not-be-returned"}
        client = _client(monkeypatch, tmp_path, payload)
        response = client.get("/v1/program/status", headers=_owner_headers())
        assert response.status_code == 503
        assert response.json()["reason"] == "program_status_sensitive_data_rejected"
        assert b"must-not-be-returned" not in response.content
    finally:
        execution_api._EXECUTION_KEY_HASHES = old_hashes
        execution_api._EXECUTION_AUTH_CONFIGURATION_ERROR = old_error


def test_tracked_program_status_document_satisfies_wallboard_projection_contract(monkeypatch):
    monkeypatch.setenv(program_status_api.PROGRAM_STATUS_MAX_AGE_ENV, "86400")
    projection, digest = program_status_api.load_program_status_projection(
        path=ROOT / "release" / "program-status.json",
    )
    assert projection["source"] == "program-ledger/home"
    assert projection["gate_progress"]["total"] == 11
    assert projection["source_sha256"] == f"sha256:{digest}"
    assert projection["availability"] in {"partial", "stale"}
