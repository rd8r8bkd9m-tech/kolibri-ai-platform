from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from provider_gateway import FACTORY_IMAGE_EVIDENCE_SCHEMA, ProviderGateway  # noqa: E402


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _hash(value):
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _completed_image_task(task_id: str, *, corrupt: bool = False):
    attempt_id = f"{task_id}-attempt-1"
    evidence_payload = {
        "schema_version": FACTORY_IMAGE_EVIDENCE_SCHEMA,
        "task_id": task_id,
        "attempt_id": attempt_id,
        "fencing_token": 1,
        "node_id": "dynamic-image-worker",
        "agent_id": "agent-image",
        "content_sha256": hashlib.sha256(TINY_PNG).hexdigest(),
        "media_type": "image/png",
        "size_bytes": len(TINY_PNG),
    }
    return {
        "task_id": task_id,
        "state": "completed",
        "attempt_id": attempt_id,
        "fencing_token": 1,
        "lease_owner": "dynamic-image-worker:agent-image",
        "completion_evidence": {
            "result_sha256": f"sha256:{'a' * 64}",
            "binding_sha256": f"sha256:{'b' * 64}",
        },
        "completion_verifier": {
            "verifier": "control-plane/home",
            "verdict": "passed",
            "checks": {"task": True, "attempt": True, "fencing_token": True},
        },
        "result": {
            "status": "completed",
            "attempt_id": attempt_id,
            "fencing_token": 1,
            "node_id": "dynamic-image-worker",
            "agent_id": "agent-image",
            "image_b64": base64.b64encode(
                b"not-an-image" if corrupt else TINY_PNG,
            ).decode("ascii"),
            "image_evidence": {
                **evidence_payload,
                "binding_sha256": _hash(evidence_payload),
                "verdict": "passed",
            },
        },
    }


def test_image_gateway_dispatches_without_static_node_and_verifies_bytes(monkeypatch):
    gateway = ProviderGateway(provider_order=("factory",), timeout=5)
    submitted = []

    def request(method, path, *, payload=None, timeout=None):
        del timeout
        if method == "GET" and path.startswith("/v1/nodes"):
            return {
                "nodes": [{
                    "node_id": "dynamic-image-worker",
                    "membership_scope": "active",
                    "health": "online",
                    "freshness": "fresh",
                    "heartbeat_age_seconds": 1,
                    "schedulable": True,
                    "capabilities": ["image_generation"],
                }],
            }, None
        if method == "POST" and path == "/v1/tasks":
            submitted.append(payload)
            return {"task_id": payload["task_id"], "state": "queued"}, None
        if method == "GET" and path.startswith("/v1/tasks/"):
            return _completed_image_task(submitted[0]["task_id"]), None
        raise AssertionError((method, path, payload))

    monkeypatch.setattr(gateway, "_factory_request", request)
    result = gateway.generate_image("Нарисуй птицу", "resp-image-1")

    assert result.status == "completed"
    assert result.content == TINY_PNG
    assert result.media_type == "image/png"
    assert result.content_sha256 == hashlib.sha256(TINY_PNG).hexdigest()
    assert len(result.factory_binding_sha256) == 64
    assert gateway.verified_image_generation_health() is True
    assert submitted[0]["required_capability"] == "image_generation"
    assert "target_node" not in submitted[0]
    assert submitted[0]["source"]["control_plane"] == "home"


def test_image_gateway_rejects_worker_prose_or_corrupt_transported_bytes(monkeypatch):
    gateway = ProviderGateway(provider_order=("factory",), timeout=5)
    task_id = []

    def request(method, path, *, payload=None, timeout=None):
        del timeout
        if method == "GET" and path.startswith("/v1/nodes"):
            return {"nodes": [{
                "node_id": "dynamic-image-worker",
                "health": "online",
                "freshness": "fresh",
                "heartbeat_age_seconds": 1,
                "schedulable": True,
                "capabilities": ["image_generation"],
            }]}, None
        if method == "POST" and path == "/v1/tasks":
            task_id.append(payload["task_id"])
            return {"task_id": payload["task_id"], "state": "queued"}, None
        if method == "GET" and path.startswith("/v1/tasks/"):
            return _completed_image_task(task_id[0], corrupt=True), None
        raise AssertionError((method, path, payload))

    monkeypatch.setattr(gateway, "_factory_request", request)
    result = gateway.generate_image("Нарисуй птицу", "resp-image-corrupt")

    assert result.status == "failed"
    assert result.content == b""
    assert result.technical["error_type"] == "factory_image_evidence_invalid"
    assert gateway.verified_image_generation_health() is False
