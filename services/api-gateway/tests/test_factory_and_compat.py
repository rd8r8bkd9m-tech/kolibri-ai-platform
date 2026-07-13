from __future__ import annotations

from conftest import auth_headers, bootstrap

NODE_HEADERS = {"X-Kolibri-Node-Token": "node-secret"}
DEVELOPER_KEY = "sk-" + "kolibri-" + "test-developer-key"


def test_factory_fencing_artifact_and_verifier_gate(client):
    token, project_id = bootstrap(client, "owner")
    headers = auth_headers(token)
    node = client.post(
        "/v1/nodes/register",
        headers=NODE_HEADERS,
        json={"node_id": "worker-01", "hostname": "worker-01", "capabilities": ["health.probe"]},
    )
    assert node.status_code == 200, node.text
    task = client.post(
        "/v1/tasks",
        headers=headers,
        json={"project_id": project_id, "title": "Health proof", "kind": "health_probe", "required_capabilities": ["health.probe"], "required_artifacts": ["RESULT.md"]},
    ).json()
    lease = client.post(
        "/v1/tasks/lease",
        headers=NODE_HEADERS,
        json={"node_id": "worker-01", "capabilities": ["health.probe"], "lease_seconds": 60},
    ).json()["task"]
    assert lease["id"] == task["id"]
    incomplete = client.post(
        f"/v1/tasks/{task['id']}/complete",
        headers=NODE_HEADERS,
        json={"node_id": "worker-01", "lease_id": lease["lease_id"], "fencing_token": lease["fencing_token"], "result": {"ok": True}},
    )
    assert incomplete.status_code == 422
    uploaded = client.post(
        f"/v1/tasks/{task['id']}/artifacts",
        headers=NODE_HEADERS,
        data={"node_id": "worker-01", "lease_id": lease["lease_id"], "fencing_token": str(lease["fencing_token"])},
        files={"file": ("RESULT.md", b"# Worker result\nPONG\n", "text/markdown")},
    )
    assert uploaded.status_code == 200, uploaded.text
    completed = client.post(
        f"/v1/tasks/{task['id']}/complete",
        headers=NODE_HEADERS,
        json={"node_id": "worker-01", "lease_id": lease["lease_id"], "fencing_token": lease["fencing_token"], "result": {"ok": True}},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    stale = client.post(
        f"/v1/tasks/{task['id']}/complete",
        headers=NODE_HEADERS,
        json={"node_id": "worker-01", "lease_id": "old", "fencing_token": 0, "result": {}},
    )
    assert stale.status_code == 409
    events = client.get(f"/v1/tasks/{task['id']}/events", headers=headers).json()["data"]
    assert {event["type"] for event in events} >= {"task.created", "lease.granted", "artifact.written", "verifier.checked", "task.completed"}


def test_openai_compatibility_is_fail_closed_without_provider(client):
    token, _ = bootstrap(client)
    headers = auth_headers(token)
    models = client.get("/v1/models", headers=headers)
    assert models.status_code == 200
    assert [model["id"] for model in models.json()["data"]] == ["kolibri"]
    images = client.post("/v1/images/generations", headers=headers, json={"model": "gpt-image-1", "prompt": "bird"})
    assert images.status_code == 403
    assert images.json()["error"]["code"] == "insufficient_permissions"
    developer_images = client.post(
        "/v1/images/generations",
        headers={"Authorization": f"Bearer {DEVELOPER_KEY}"},
        json={"model": "gpt-image-1", "prompt": "bird"},
    )
    assert developer_images.status_code == 503
    assert developer_images.json()["error"]["code"] == "upstream_not_configured"
    unknown = client.get("/v1/not-a-real-resource", headers=headers)
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "resource_not_found"


def test_expired_lease_is_reassigned_with_new_fence_and_old_worker_is_rejected(client):
    token, project_id = bootstrap(client, "owner")
    owner_headers = auth_headers(token)
    for node_id in ["worker-a", "worker-b"]:
        registered = client.post(
            "/v1/nodes/register",
            headers=NODE_HEADERS,
            json={"node_id": node_id, "hostname": node_id, "capabilities": ["health.probe"]},
        )
        assert registered.status_code == 200
    task = client.post(
        "/v1/tasks",
        headers=owner_headers,
        json={
            "project_id": project_id,
            "title": "Reassignment proof",
            "kind": "health_probe",
            "required_capabilities": ["health.probe"],
            "required_artifacts": ["RESULT.md"],
            "max_attempts": 2,
        },
    ).json()
    first = client.post(
        "/v1/tasks/lease",
        headers=NODE_HEADERS,
        json={"node_id": "worker-a", "capabilities": ["health.probe"], "lease_seconds": 60},
    ).json()["task"]
    # Move lease into the past without sleeping; the next lease operation must reap it.
    client.app.state.store.execute(
        "UPDATE tasks SET lease_until=? WHERE id=?",
        ("2000-01-01T00:00:00+00:00", task["id"]),
    )
    second = client.post(
        "/v1/tasks/lease",
        headers=NODE_HEADERS,
        json={"node_id": "worker-b", "capabilities": ["health.probe"], "lease_seconds": 60},
    ).json()["task"]
    assert second["id"] == task["id"]
    assert second["attempt"] == 2
    assert second["fencing_token"] > first["fencing_token"]
    assert second["lease_id"] != first["lease_id"]

    late = client.post(
        f"/v1/tasks/{task['id']}/complete",
        headers=NODE_HEADERS,
        json={
            "node_id": "worker-a",
            "lease_id": first["lease_id"],
            "fencing_token": first["fencing_token"],
            "result": {"late": True},
        },
    )
    assert late.status_code == 409

    artifact = client.post(
        f"/v1/tasks/{task['id']}/artifacts",
        headers=NODE_HEADERS,
        data={
            "node_id": "worker-b",
            "lease_id": second["lease_id"],
            "fencing_token": str(second["fencing_token"]),
        },
        files={"file": ("RESULT.md", b"# Reassigned worker result\nhealthy\n", "text/markdown")},
    )
    assert artifact.status_code == 200
    completed = client.post(
        f"/v1/tasks/{task['id']}/complete",
        headers=NODE_HEADERS,
        json={
            "node_id": "worker-b",
            "lease_id": second["lease_id"],
            "fencing_token": second["fencing_token"],
            "result": {"healthy": True, "worker": "worker-b"},
        },
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    events = client.get(f"/v1/tasks/{task['id']}/events", headers=owner_headers).json()["data"]
    event_types = [event["type"] for event in events]
    assert "lease.expired" in event_types
    assert event_types.count("lease.granted") == 2
