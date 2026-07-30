from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import httpx
import app.direct_model_runtime as direct_model_runtime
import app.main as main_module
from app.config import Settings
from app.main import create_app
from app.owner_bootstrap import promote_registered_owner
from app.product_entitlements import CONSTRUCTION_ESTIMATES_ENTITLEMENT
from app.provider_authority import (
    ProviderAuthorityClient,
    ProviderAuthoritySettings,
)
from app.provider_enrollment_worker import ProviderEnrollmentWorker
from fastapi.testclient import TestClient


ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
DEVICE = {
    "platform": "ios",
    "deviceName": "Public estimate journey iPhone",
    "appVersion": "1.0.0",
}
PROVIDER_ENROLLMENT_NONCE = "958ca508-452e-41d0-a98f-0e8d558365b7"


class _EstimateIntakeTransport:
    """Deterministic external-runtime boundary for the public journey test."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def complete(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        assert kwargs["execution_profile"] == "estimate-intake"
        assert kwargs["output_schema"] is not None
        return json.dumps(
            {
                "title": "Механизированная штукатурка стен 358 м²",
                "region": "Республика Татарстан",
                "wallAreaM2": "358",
                "averageThicknessMm": "15",
                "material": "gypsum",
                "applicationMethod": "mechanized",
                "wastePercent": "10",
                "protectionAreaM2": "89.5",
                "wallHeightM": "3",
                "beaconSpacingM": "1.5",
                "cornerLengthM": "0",
                "meshAreaPercent": "10",
                "slopesAreaM2": "0",
                "plasterBagWeightKg": "30",
                "primerPasses": 1,
                "wasteRemovalTrips": "1",
                "assumptions": [
                    "Неуказанные технологические параметры требуют проверки."
                ],
                "candidatePrices": [],
            },
            ensure_ascii=False,
        )


def _settings(database_path: Path) -> Settings:
    return replace(
        Settings.for_testing(database_url=database_path),
        direct_model_runtime_enabled=True,
        product_run_poll_seconds=0.05,
        product_run_idle_seconds=0.05,
    )


def _register_owner(
    client: TestClient,
    settings: Settings,
) -> dict[str, object]:
    response = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={
            "email": "owner@example.com",
            "name": "Owner",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    promote_registered_owner(settings, email="owner@example.com")
    return response.json()["user"]


def _mobile_register(
    client: TestClient,
    *,
    email: str,
    device_name: str,
) -> dict[str, object]:
    response = client.post(
        "/v1/mobile/auth/register",
        json={
            "email": email,
            "name": email.split("@", 1)[0],
            "password": PASSWORD,
            "device": {**DEVICE, "deviceName": device_name},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _bearer(registration: dict[str, object]) -> dict[str, str]:
    access_token = registration["accessToken"]
    assert isinstance(access_token, str)
    return {"Authorization": f"Bearer {access_token}"}


def _grant_estimate_access(
    client: TestClient,
    *,
    user_id: object,
) -> None:
    assert isinstance(user_id, str)
    csrf = client.cookies.get("kolibri_v3_csrf")
    assert csrf
    response = client.patch(
        (
            f"/v1/platform-admin/users/{user_id}/entitlements/"
            f"{CONSTRUCTION_ESTIMATES_ENTITLEMENT}"
        ),
        headers={**ORIGIN, "X-CSRF-Token": csrf},
        json={"expectedEpoch": 0, "status": "active"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"


def _connect_codex_through_authority(
    client: TestClient,
    settings: Settings,
) -> None:
    csrf = client.cookies.get("kolibri_v3_csrf")
    assert csrf
    accepted = client.post(
        "/v1/provider-connections/codex-cli/enrollment-intents",
        headers={
            **ORIGIN,
            "X-CSRF-Token": csrf,
            "Idempotency-Key": PROVIDER_ENROLLMENT_NONCE,
        },
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["provider"]["status"] == "pending"

    def handler(request: httpx.Request) -> httpx.Response:
        command = json.loads(request.content)
        payload = command["payload"]
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={
                "schema_id": "kolibri.product.provider.enrollment_status",
                "schema_version": "1.0",
                "tenant_id": payload["tenant_id"],
                "intent_id": payload["intent_id"],
                "provider_id": payload["provider_id"],
                "status": "connected",
                "auth_flow_supported": False,
                "last_verified_at": "2026-07-30T10:00:00+00:00",
                "error": None,
            },
        )

    authority = ProviderAuthorityClient(
        ProviderAuthoritySettings(
            command_url=(
                "http://127.0.0.1:18445"
                "/v1/runtime/product-provider-enrollment-intents"
            ),
            bearer_token="a" * 32,
            identity_hmac_key="b" * 32,
        ),
        transport=httpx.MockTransport(handler),
    )
    worker = ProviderEnrollmentWorker(
        database_url=settings.database_url,
        settings=settings,
        authority=authority,
    )
    assert worker.run_once() is True
    listing = client.get("/v1/provider-connections")
    assert listing.status_code == 200, listing.text
    codex = next(
        provider
        for provider in listing.json()["providers"]
        if provider["id"] == "codex-cli"
    )
    assert codex["status"] == "connected"


def _run_payload() -> dict[str, object]:
    return {
        "threadId": "thread_public_estimate_journey_01",
        "runId": "run_public_estimate_journey_01",
        "state": None,
        "messages": [
            {
                "id": "message_public_estimate_journey_01",
                "role": "user",
                "content": (
                    "Составь смету на 358 м² механизированной гипсовой "
                    "штукатурки стен слоем 15 мм в Татарстане."
                ),
            }
        ],
        "tools": [],
        "context": [],
        "forwardedProps": {
            "agentProfile": "auto",
            "executionMode": "standard",
            "accessMode": "standard",
        },
    }


def _sse_events(response_text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in response_text.splitlines():
        if not line.startswith("data: "):
            continue
        value = json.loads(line.removeprefix("data: "))
        assert isinstance(value, dict)
        events.append(value)
    return events


def test_public_agui_materializes_tenant_scoped_estimate_without_db_seeding(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    database_path = tmp_path / "public-estimate-journey.db"
    settings = _settings(database_path)
    transport = _EstimateIntakeTransport()
    registry = direct_model_runtime._legacy_runtime_registry(
        settings,
        codex_transport=transport,
        mimo_transport=None,
        mimo_developer_transport=None,
    )
    monkeypatch.setattr(
        main_module,
        "build_agent_runtime_registry",
        lambda *_args, **_kwargs: registry,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        _register_owner(client, settings)
        _connect_codex_through_authority(client, settings)

        customer = _mobile_register(
            client,
            email="customer@example.com",
            device_name="Customer iPhone",
        )
        other_tenant = _mobile_register(
            client,
            email="other@example.com",
            device_name="Other tenant iPhone",
        )
        unentitled = _mobile_register(
            client,
            email="unentitled@example.com",
            device_name="Unentitled iPhone",
        )
        _grant_estimate_access(client, user_id=customer["user"]["id"])
        _grant_estimate_access(client, user_id=other_tenant["user"]["id"])

        run = client.post(
            "/v1/chat/ag-ui",
            headers={
                **_bearer(customer),
                "Accept": "text/event-stream",
            },
            json=_run_payload(),
        )
        assert run.status_code == 200, run.text
        assert run.headers["content-type"].startswith("text/event-stream")
        internal_run_id = run.headers["x-kolibri-run-id"]
        events = _sse_events(run.text)
        assert events[0]["type"] == "RUN_STARTED"
        assert events[-1] == {
            **events[-1],
            "type": "RUN_FINISHED",
            "outcome": {"type": "success"},
        }
        tool_starts = {
            event["toolCallName"]: event["toolCallId"]
            for event in events
            if event["type"] == "TOOL_CALL_START"
        }
        assert "estimate_engine_calculate" in tool_starts
        present_tool_call_id = tool_starts["present"]
        present_args_event = next(
            event
            for event in events
            if event["type"] == "TOOL_CALL_ARGS"
            and event["toolCallId"] == present_tool_call_id
        )
        present_args = json.loads(present_args_event["delta"])
        assert present_args["$type"] == "EstimateEditor"
        assert transport.calls

        threads = client.get(
            "/v1/chat/threads",
            headers=_bearer(customer),
        )
        assert threads.status_code == 200, threads.text
        assert len(threads.json()["threads"]) == 1
        thread = threads.json()["threads"][0]
        assert thread["id"] == _run_payload()["threadId"]
        project_id = thread["projectId"]
        assert isinstance(project_id, str)
        assert present_args["projectId"] == project_id

        estimate = client.get(
            f"/v1/projects/{project_id}/estimate",
            headers=_bearer(customer),
        )
        assert estimate.status_code == 200, estimate.text
        estimate_value = estimate.json()
        assert estimate_value["projectId"] == project_id
        assert estimate_value["version"] == 1
        assert estimate_value["status"] == "draft"
        assert estimate_value["estimateTitle"].startswith(
            "Механизированная гипсовая штукатурка"
        )
        assert len(estimate_value["rows"]) >= 3
        assert {"work", "material", "service"} <= {
            row["kind"] for row in estimate_value["rows"]
        }
        assert estimate_value["pricing"]["status"] == "unpriced"
        assert estimate_value["totals"]["total"] != "0.00"

        versions = client.get(
            f"/v1/projects/{project_id}/estimate/versions",
            headers=_bearer(customer),
        )
        assert versions.status_code == 200, versions.text
        assert versions.json()["versions"] == [
            {
                **versions.json()["versions"][0],
                "version": 1,
                "status": "draft",
                "originType": "engine_calculation",
                "originRunId": internal_run_id,
                "lineage": None,
            }
        ]

        messages = client.get(
            f"/v1/chat/threads/{thread['id']}/messages",
            headers=_bearer(customer),
        )
        assert messages.status_code == 200, messages.text
        tool_message = messages.json()["messages"][-1]["content"][0]
        assert tool_message["type"] == "tool-call"
        assert tool_message["args"]["$type"] == "EstimateEditor"
        assert tool_message["args"]["projectId"] == project_id
        assert tool_message["result"]["estimateVersion"] == 1

        documents = client.get(
            "/v1/documents",
            headers=_bearer(customer),
        )
        assert documents.status_code == 200, documents.text
        assert [item["projectId"] for item in documents.json()["documents"]] == [
            project_id
        ]

        hidden = client.get(
            f"/v1/projects/{project_id}/estimate",
            headers=_bearer(other_tenant),
        )
        assert hidden.status_code == 404
        assert hidden.json()["code"] == "estimate_not_found"

        denied = client.get(
            f"/v1/projects/{project_id}/estimate",
            headers=_bearer(unentitled),
        )
        assert denied.status_code == 403
        assert denied.json()["code"] == "product_entitlement_required"
