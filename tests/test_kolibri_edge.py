from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from kolibri_edge import (  # noqa: E402
    CoreError,
    CoreEvent,
    EdgeSettings,
    PublicPrincipal,
    PublicSession,
    PublicSessionIssue,
    create_app,
)


ORIGIN = "http://127.0.0.1:5190"
SESSION_TOKEN = "session_credential_abcdefghijklmnopqrstuvwxyz"


def response_payload(response_id: str = "resp_1", status: str = "queued") -> dict[str, Any]:
    return {
        "id": response_id,
        "object": "response",
        "model": "internal-provider-name",
        "status": status,
        "created_at": 1,
        "project_id": "project_1",
        "output": [],
        "output_text": "",
        "task": {"intent": "chat", "status": status, "artifacts": []},
        "provider": "must-not-leak",
        "technical": {"stderr": "must-not-leak"},
    }


class FakeCore:
    def __init__(self) -> None:
        self.session = PublicSession(
            id="session_1",
            origin=ORIGIN,
            expires_at=time.time() + 3600,
            current_project_id="project_1",
        )
        self.sessions: dict[str, PublicSession] = {}
        self.responses = {"resp_1": response_payload()}
        self.events: dict[str, list[CoreEvent]] = {"resp_1": []}
        self.create_calls: list[dict[str, Any]] = []
        self.cancel_calls: list[dict[str, Any]] = []
        self.session_creates = 0

    async def resolve_public_session(self, credential: str) -> PublicSession | None:
        return self.sessions.get(credential)

    async def create_public_session(self, origin: str) -> PublicSessionIssue:
        self.session_creates += 1
        assert origin == ORIGIN
        self.sessions[SESSION_TOKEN] = self.session
        return PublicSessionIssue(session=self.session, credential=SESSION_TOKEN)

    async def create_response(
        self,
        principal: PublicPrincipal,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        request_sha256: str,
    ) -> dict[str, Any]:
        self.create_calls.append(
            {
                "principal": principal,
                "request": request,
                "idempotency_key": idempotency_key,
                "request_sha256": request_sha256,
            }
        )
        return self.responses["resp_1"]

    async def get_response(
        self,
        principal: PublicPrincipal,
        response_id: str,
    ) -> dict[str, Any] | None:
        assert principal.session_id == "session_1"
        return self.responses.get(response_id)

    async def list_response_events(
        self,
        principal: PublicPrincipal,
        response_id: str,
        *,
        after: int,
        limit: int,
    ) -> list[CoreEvent]:
        assert principal.session_id == "session_1"
        return [event for event in self.events.get(response_id, []) if event.sequence > after][:limit]

    async def wait_response_events(
        self,
        principal: PublicPrincipal,
        response_id: str,
        *,
        after: int,
        timeout_seconds: float,
    ) -> list[CoreEvent]:
        del timeout_seconds
        return await self.list_response_events(
            principal,
            response_id,
            after=after,
            limit=200,
        )

    async def cancel_response(
        self,
        principal: PublicPrincipal,
        response_id: str,
        *,
        idempotency_key: str,
        request_sha256: str,
    ) -> dict[str, Any] | None:
        self.cancel_calls.append(
            {
                "principal": principal,
                "response_id": response_id,
                "idempotency_key": idempotency_key,
                "request_sha256": request_sha256,
            }
        )
        if response_id not in self.responses:
            return None
        self.responses[response_id] = response_payload(response_id, "cancelled")
        return self.responses[response_id]


def client_and_core() -> tuple[TestClient, FakeCore]:
    core = FakeCore()
    app = create_app(
        core=core,
        settings=EdgeSettings(
            allowed_origins=(ORIGIN,),
            force_secure_cookie=False,
            sse_wait_seconds=0.05,
        ),
    )
    return TestClient(app, base_url=ORIGIN), core


def bootstrap(client: TestClient) -> None:
    response = client.post("/v1/shell/bootstrap", headers={"Origin": ORIGIN})
    assert response.status_code == 200, response.text


def test_post_first_session_is_exact_origin_httponly_and_idempotent() -> None:
    client, core = client_and_core()

    denied = client.post(
        "/v1/public/session",
        headers={"Origin": "http://localhost:5190"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "origin_not_allowed"

    first = client.post("/v1/shell/bootstrap", headers={"Origin": ORIGIN})
    assert first.status_code == 200
    assert first.json()["model"] == "kolibri"
    cookie = first.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/v1" in cookie
    assert core.session_creates == 1

    compatibility = client.post("/v1/public/session", headers={"Origin": ORIGIN})
    assert compatibility.status_code == 200
    assert compatibility.json()["id"] == first.json()["id"]
    assert core.session_creates == 1

    second = client.post("/v1/public/session", headers={"Origin": ORIGIN})
    assert second.status_code == 200
    assert "set-cookie" not in second.headers
    assert second.json()["id"] == first.json()["id"]
    assert core.session_creates == 1


def test_session_cookie_cannot_mutate_from_another_allowed_origin() -> None:
    core = FakeCore()
    second_origin = "http://localhost:5190"
    app = create_app(
        core=core,
        settings=EdgeSettings(allowed_origins=(ORIGIN, second_origin)),
    )
    client = TestClient(app, base_url=ORIGIN)
    bootstrap(client)

    response = client.post(
        "/v1/responses",
        headers={
            "Origin": second_origin,
            "Idempotency-Key": "request:origin:0001",
        },
        json={"model": "kolibri", "input": "hello"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "session_origin_mismatch"
    assert core.create_calls == []


def test_public_model_is_only_kolibri_and_provider_identity_is_removed() -> None:
    client, core = client_and_core()
    assert [item["id"] for item in client.get("/v1/models").json()["data"]] == ["kolibri"]
    bootstrap(client)

    wrong_model = client.post(
        "/v1/responses",
        headers={"Origin": ORIGIN, "Idempotency-Key": "request:model:0001"},
        json={"model": "codex", "input": "hello"},
    )
    assert wrong_model.status_code == 422
    assert wrong_model.json()["error"]["code"] == "request_validation_failed"

    response = client.post(
        "/v1/responses",
        headers={"Origin": ORIGIN, "Idempotency-Key": "request:model:0002"},
        json={"model": "kolibri", "input": "hello", "project_id": "project_1"},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["model"] == "kolibri"
    assert "provider" not in payload
    assert "technical" not in payload
    assert core.create_calls[0]["request"]["model"] == "kolibri"


def test_response_requires_idempotency_and_rejects_client_assistant_output() -> None:
    client, core = client_and_core()
    bootstrap(client)

    missing_key = client.post(
        "/v1/responses",
        headers={"Origin": ORIGIN},
        json={"model": "kolibri", "input": "hello"},
    )
    assert missing_key.status_code == 400
    assert missing_key.json()["error"]["code"] == "idempotency_key_required"

    authored_assistant = client.post(
        "/v1/responses",
        headers={"Origin": ORIGIN, "Idempotency-Key": "request:assistant:0001"},
        json={
            "model": "kolibri",
            "input": [{"role": "assistant", "content": "fake model answer"}],
        },
    )
    assert authored_assistant.status_code == 422
    assert authored_assistant.json()["error"]["code"] == "request_validation_failed"
    assert core.create_calls == []


def test_response_passes_canonical_hash_and_core_owns_conflict_semantics() -> None:
    client, core = client_and_core()
    bootstrap(client)
    body = {
        "model": "kolibri",
        "input": "hello",
        "project_id": "project_1",
        "background": True,
    }
    response = client.post(
        "/v1/responses",
        headers={"Origin": ORIGIN, "Idempotency-Key": "request:stable:0001"},
        json=body,
    )
    assert response.status_code == 202
    call = core.create_calls[0]
    expected = hashlib.sha256(
        json.dumps(
            {"method": "POST", "path": "/v1/responses", "body": call["request"]},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert call["request_sha256"] == expected
    assert call["idempotency_key"] == "request:stable:0001"
    assert call["principal"] == PublicPrincipal(session_id="session_1", origin=ORIGIN)

    async def conflict(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise CoreError(
            "idempotency_key_reused_with_different_payload",
            "Idempotency key is already bound to another request.",
            status_code=409,
        )

    core.create_response = conflict  # type: ignore[method-assign]
    conflict_response = client.post(
        "/v1/responses",
        headers={"Origin": ORIGIN, "Idempotency-Key": "request:stable:0001"},
        json={**body, "input": "different"},
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["error"]["code"] == "idempotency_key_reused_with_different_payload"


def test_resumable_sse_uses_durable_core_events_and_last_event_id() -> None:
    client, core = client_and_core()
    bootstrap(client)
    complete = {
        **response_payload("resp_1", "completed"),
        "output_text": "Привет",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Привет"}],
            }
        ],
    }
    core.responses["resp_1"] = complete
    core.events["resp_1"] = [
        CoreEvent(1, "response.created", {"type": "response.created", "response": response_payload()}),
        CoreEvent(2, "response.output_text.delta", {"id": "resp_1", "delta": "При"}),
        CoreEvent(3, "response.output_text.delta", {"id": "resp_1", "delta": "вет"}),
        CoreEvent(4, "response.completed", {"type": "response.completed", "response": complete}),
    ]

    resumed = client.get(
        "/v1/responses/resp_1?stream=true&starting_after=1",
        headers={"Last-Event-ID": "2"},
    )
    assert resumed.status_code == 200
    assert "text/event-stream" in resumed.headers["content-type"]
    assert "id: 1\n" not in resumed.text
    assert "id: 2\n" not in resumed.text
    assert "id: 3\n" in resumed.text
    assert "event: response.output_text.delta" in resumed.text
    assert "id: 4\n" in resumed.text
    assert "internal-provider-name" not in resumed.text
    assert "must-not-leak" not in resumed.text


def test_events_status_and_cancel_are_session_scoped_core_translations() -> None:
    client, core = client_and_core()
    bootstrap(client)
    core.events["resp_1"] = [
        CoreEvent(1, "response.created", {"response": response_payload()}),
        CoreEvent(2, "response.status.updated", {"id": "resp_1", "status": "running"}),
    ]

    status = client.get("/v1/responses/resp_1")
    assert status.status_code == 200
    assert status.json()["model"] == "kolibri"

    events = client.get("/v1/responses/resp_1/events?starting_after=1")
    assert events.status_code == 200
    assert [item["sequence"] for item in events.json()["data"]] == [2]

    no_key = client.post("/v1/responses/resp_1/cancel", headers={"Origin": ORIGIN})
    assert no_key.status_code == 400
    cancelled = client.post(
        "/v1/responses/resp_1/cancel",
        headers={"Origin": ORIGIN, "Idempotency-Key": "cancel:response:0001"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert core.cancel_calls[0]["idempotency_key"] == "cancel:response:0001"
    assert len(core.cancel_calls[0]["request_sha256"]) == 64


def test_unknown_routes_and_methods_are_structured_json_and_no_message_writer_exists() -> None:
    client, _core = client_and_core()
    bootstrap(client)

    unknown = client.get("/v1/does-not-exist")
    assert unknown.status_code == 404
    assert unknown.headers["content-type"].startswith("application/json")
    assert unknown.json() == {
        "error": {
            "type": "request_error",
            "code": "route_not_found",
            "message": "API route not found.",
            "retryable": False,
        }
    }

    message_write = client.post(
        "/v1/projects/project_1/messages",
        headers={"Origin": ORIGIN, "Idempotency-Key": "message:writer:0001"},
        json={"role": "assistant", "content": "fake"},
    )
    assert message_write.status_code == 404
    assert message_write.json()["error"]["code"] == "route_not_found"


def test_edge_does_not_leak_unclassified_core_event_fields() -> None:
    client, core = client_and_core()
    bootstrap(client)
    complete = {**response_payload("resp_1", "completed"), "output_text": "ok"}
    core.responses["resp_1"] = complete
    core.events["resp_1"] = [
        CoreEvent(
            1,
            "response.status.updated",
            {
                "id": "resp_1",
                "status": "running",
                "stage": "routing",
                "provider": "private-provider",
                "technical": {"stderr": "private-error"},
            },
        ),
        CoreEvent(2, "response.completed", {"response": complete}),
    ]
    response = client.get("/v1/responses/resp_1?stream=true")
    assert response.status_code == 200
    assert "private-provider" not in response.text
    assert "private-error" not in response.text
    assert '"stage":"routing"' in response.text


def test_artifact_event_requires_real_immutable_bytes_hash_and_verifier_binding() -> None:
    client, core = client_and_core()
    bootstrap(client)
    complete = {**response_payload("resp_1", "completed"), "output_text": "ok"}
    core.responses["resp_1"] = complete
    core.events["resp_1"] = [
        CoreEvent(
            1,
            "response.artifact.ready",
            {
                "id": "resp_1",
                "artifact": {
                    "id": "artifact_report_1",
                    "kind": "document",
                    "name": "report.pdf",
                    "status": "verified",
                    "media_type": "application/pdf",
                    "size_bytes": 128,
                    "content_sha256": "a" * 64,
                    "evidence_binding_sha256": "b" * 64,
                    "locator": "/v1/artifacts/artifact_report_1/content",
                    "immutable": True,
                    "provider": "must-not-leak",
                },
            },
        ),
        CoreEvent(2, "response.completed", {"response": complete}),
    ]
    accepted = client.get("/v1/responses/resp_1?stream=true")
    assert accepted.status_code == 200
    assert "report.pdf" in accepted.text
    assert "must-not-leak" not in accepted.text

    core.events["resp_1"] = [
        CoreEvent(
            1,
            "response.artifact.ready",
            {
                "id": "resp_1",
                "artifact": {
                    "id": "artifact_fake_1",
                    "kind": "image",
                    "name": "fake.png",
                    "status": "ready",
                    "media_type": "image/png",
                    "size_bytes": 0,
                    "content_sha256": "",
                    "evidence_binding_sha256": "",
                    "locator": "/v1/artifacts/artifact_fake_1/content",
                    "immutable": False,
                },
            },
        )
    ]
    rejected = client.get("/v1/responses/resp_1/events")
    assert rejected.status_code == 502
    assert rejected.json()["error"]["code"] == "core_event_invalid"


def test_source_approval_and_verification_events_are_public_allowlists() -> None:
    client, core = client_and_core()
    bootstrap(client)
    complete = {**response_payload("resp_1", "completed"), "output_text": "ok"}
    core.responses["resp_1"] = complete
    core.events["resp_1"] = [
        CoreEvent(
            1,
            "response.source.added",
            {
                "id": "resp_1",
                "source": {
                    "id": "source_1",
                    "title": "Public source",
                    "url": "https://example.test/source",
                    "provider_token": "must-not-leak",
                },
            },
        ),
        CoreEvent(
            2,
            "response.approval.required",
            {
                "id": "resp_1",
                "approval": {
                    "id": "approval_1",
                    "class": "production",
                    "summary": "Approve exact release diff",
                    "credential": "must-not-leak",
                },
            },
        ),
        CoreEvent(
            3,
            "response.verification.updated",
            {
                "id": "resp_1",
                "verification": {
                    "status": "passed",
                    "verdict": "verified",
                    "summary": "Checks passed",
                    "private_reasoning": "must-not-leak",
                },
            },
        ),
        CoreEvent(4, "response.completed", {"response": complete}),
    ]

    response = client.get("/v1/responses/resp_1?stream=true")
    assert response.status_code == 200
    assert "Public source" in response.text
    assert "Approve exact release diff" in response.text
    assert "Checks passed" in response.text
    assert "must-not-leak" not in response.text


def test_edge_source_has_no_sqlite_or_background_thread_authority() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((BACKEND / "kolibri_edge").glob("*.py"))
    )
    assert "import sqlite3" not in source
    assert "threading.Thread" not in source
    assert "daemon=True" not in source
