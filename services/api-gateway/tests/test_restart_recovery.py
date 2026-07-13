from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

from fastapi.testclient import TestClient


def test_restart_reconciles_same_response_without_duplicate_assistant(tmp_path: Path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("KOLIBRI_ENV", "test")
    monkeypatch.setenv("KOLIBRI_DATA_DIR", str(data))
    monkeypatch.setenv("KOLIBRI_DB_PATH", str(data / "kolibri.db"))
    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(data / "artifacts"))
    monkeypatch.setenv("KOLIBRI_SESSION_SECRET", "restart-recovery-secret")
    monkeypatch.setenv("KOLIBRI_EXPOSE_SESSION_TOKEN", "1")

    from kolibri_v2.app import create_app

    first_app = create_app()
    with TestClient(first_app) as first:
        boot = first.post("/v1/shell/bootstrap", json={"role": "client"})
        assert boot.status_code == 200
        payload = boot.json()
        session_id = payload["session"]["id"]
        token = payload["session"]["token"]
        project_id = payload["active_project"]["id"]
        request_payload = {
            "model": "kolibri",
            "project_id": project_id,
            "input": "Сделай смету на ремонт квартиры 72 м²",
            "metadata": {},
        }
        request_hash = hashlib.sha256(
            json.dumps(request_payload, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        response, created = first_app.state.store.create_response(
            session_id,
            project_id,
            request_payload,
            request_hash,
            "restart-case",
        )
        assert created
        first_app.state.store.add_message(project_id, "user", request_payload["input"], response["id"] + ":user")
        first_app.state.store.add_message(project_id, "assistant", "", response["id"])
        first_app.state.store.update_response(response["id"], status="running")
        first_app.state.store.append_response_event(
            response["id"], "response.status.updated", {"status": "running"}
        )
        response_id = response["id"]

    second_app = create_app()
    with TestClient(second_app) as second:
        headers = {"Authorization": f"Bearer {token}"}
        deadline = time.time() + 5
        current = None
        while time.time() < deadline:
            fetched = second.get(f"/v1/responses/{response_id}", headers=headers)
            assert fetched.status_code == 200, fetched.text
            current = fetched.json()
            if current["status"] == "completed":
                break
            time.sleep(0.03)
        assert current is not None
        assert current["status"] == "completed"
        assert current["id"] == response_id
        assert current["output_text"]

        messages = second.get(f"/v1/projects/{project_id}/messages", headers=headers)
        assert messages.status_code == 200
        assistant = [row for row in messages.json()["data"] if row["role"] == "assistant"]
        assert len(assistant) == 1
        assert assistant[0]["content"]

        events = second.get(
            f"/v1/responses/{response_id}/events?starting_after=0", headers=headers
        )
        assert events.status_code == 200
        types = [event["type"] for event in events.json()["data"]]
        assert "response.completed" in types
        assert any(event.get("data", {}).get("recovered") for event in events.json()["data"])
