from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import time
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


def _technology_section_fixture(
    section: str,
    rows: list[dict[str, str]],
) -> dict[str, object]:
    """Adapt transport-only rows to the technology-card generation contract."""

    section_key = hashlib.sha256(section.encode("utf-8")).hexdigest()[:10]
    resources: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        resource = {
            key: value
            for key, value in row.items()
            if key not in {"section", "unitPrice"}
        }
        resource["resourceId"] = f"resource_fixture_{section_key}_{index}"
        resource["proposedUnitPrice"] = row["unitPrice"]
        resource["quantityFormula"] = {
            "op": "constant",
            "value": row["quantity"],
            "unit": row["unit"],
        }
        resources.append(resource)
    return {
        "section": section,
        "operations": [
            {
                "operationId": f"operation_fixture_{section_key}",
                "wbsCode": f"fixture.{section_key}",
                "section": section,
                "zone": "Объект",
                "system": section,
                "sequence": 1,
                "name": f"Комплекс операций: {section}",
                "method": "Последовательная тестовая операция.",
                "unit": "компл.",
                "quantityFormula": {
                    "op": "constant",
                    "value": "1",
                    "unit": "компл.",
                },
                "resources": resources,
                "qualityChecks": ["Контроль транспортного fixture."],
            }
        ],
    }


def _price_section_fixture(
    section_payload: dict[str, object],
    *,
    region: str,
) -> dict[str, object]:
    [operation] = section_payload["operations"]  # type: ignore[index]
    resources = operation["resources"]  # type: ignore[index]
    return {
        "section": section_payload["section"],
        "candidates": [
            {
                "resourceId": resource["resourceId"],
                "unitPrice": resource["proposedUnitPrice"],
                "evidence": {
                    "sourceType": "ai_preliminary",
                    "sourceReference": (
                        "Fixture preliminary price; no external source."
                    ),
                    "sourceUrl": None,
                    "observedAt": "2026-08-02T00:00:00Z",
                    "region": region,
                    "unit": resource["unit"],
                    "vatTreatment": "not_specified",
                    "deliveryIncluded": False,
                    "validUntil": None,
                    "snapshotHash": None,
                    "confidence": "preliminary",
                },
            }
            for resource in resources  # type: ignore[union-attr]
        ],
    }


def _quoted_section(*values: object) -> str:
    for value in values:
        text = str(value or "")
        if "«" in text and "»" in text:
            return text.split("«", 1)[1].split("»", 1)[0]
    raise AssertionError("estimate role request must identify its section")


class _GeneralEstimateTransport:
    """Small deterministic boundary for tenant and persistence assertions."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.sections_by_hash: dict[str, dict[str, object]] = {}

    def complete(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        assert kwargs["output_schema"] is not None
        profile = str(kwargs["execution_profile"])
        if profile == "estimate-plan":
            return json.dumps(
                {
                    "title": "Механизированная штукатурка стен 358 м²",
                    "region": "Республика Татарстан",
                    "assumptions": [
                        "Неуказанные параметры требуют проверки.",
                    ],
                    "sections": ["Подготовка", "Штукатурные работы"],
                },
                ensure_ascii=False,
            )
        section_hash = profile.rsplit(":", 1)[-1]
        if profile.startswith("estimate-pricing:"):
            return json.dumps(
                _price_section_fixture(
                    self.sections_by_hash[section_hash],
                    region="Республика Татарстан",
                ),
                ensure_ascii=False,
            )
        if profile.startswith("estimate-review:"):
            return json.dumps({"passed": True, "issues": []})
        assert profile.startswith("estimate-role:")
        section = _quoted_section(
            kwargs.get("followup_prompt"),
            kwargs.get("initial_prompt"),
            kwargs.get("instructions"),
        )
        if section == "Подготовка":
            rows = [
                {
                    "section": section,
                    "kind": "work",
                    "description": "Устройство временной защиты рабочей зоны",
                    "unit": "шт.",
                    "quantity": "1",
                    "unitPrice": "0.00",
                    "quantityBasis": "Одна рабочая зона по тестовому scope.",
                    "priceBasis": "Предварительная AI-цена; проверить.",
                },
                {
                    "section": section,
                    "kind": "service",
                    "description": "Защита примыкающих поверхностей",
                    "unit": "м²",
                    "quantity": "89.5",
                    "unitPrice": "50.00",
                    "quantityBasis": "Предварительное условие расчёта.",
                    "priceBasis": "Предварительная AI-цена; проверить.",
                }
            ]
        else:
            rows = [
                {
                    "section": section,
                    "kind": "work",
                    "description": "Механизированное нанесение штукатурки",
                    "unit": "м²",
                    "quantity": "358",
                    "unitPrice": "500.00",
                    "quantityBasis": "Площадь из запроса пользователя.",
                    "priceBasis": "Предварительная AI-цена; проверить.",
                },
                {
                    "section": section,
                    "kind": "material",
                    "description": "Гипсовая штукатурная смесь",
                    "unit": "кг",
                    "quantity": "5907",
                    "unitPrice": "20.00",
                    "quantityBasis": "Расчётный расход с запасом; проверить.",
                    "priceBasis": "Предварительная AI-цена; проверить.",
                },
            ]
        payload = _technology_section_fixture(section, rows)
        self.sections_by_hash[section_hash] = payload
        return json.dumps(payload, ensure_ascii=False)


class _FullEstimateTransport:
    """Large-payload fixture for transport/persistence only, never semantic QA."""

    section_count = 12
    rows_per_section = 100

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.sections_by_hash: dict[str, dict[str, object]] = {}

    def complete(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        profile = kwargs["execution_profile"]
        assert kwargs["output_schema"] is not None
        if profile == "estimate-plan":
            return json.dumps(
                {
                    "title": "Полная смета девятиэтажного жилого дома",
                    "region": "Казань",
                    "assumptions": [
                        "Проектные объёмы и цены требуют подтверждения.",
                    ],
                    "sections": [
                        f"Раздел {index + 1}"
                        for index in range(self.section_count)
                    ],
                },
                ensure_ascii=False,
            )
        section_hash = profile.rsplit(":", 1)[-1]
        if profile.startswith("estimate-pricing:"):
            return json.dumps(
                _price_section_fixture(
                    self.sections_by_hash[section_hash],
                    region="Казань",
                ),
                ensure_ascii=False,
            )
        if profile.startswith("estimate-review:"):
            return json.dumps({"passed": True, "issues": []})
        assert profile.startswith("estimate-role:")
        section = _quoted_section(
            kwargs.get("followup_prompt"),
            kwargs.get("initial_prompt"),
            kwargs.get("instructions"),
        )
        kinds = ("work", "material", "equipment", "service")
        rows = [
            {
                "section": section,
                "kind": kinds[index % len(kinds)],
                "description": f"{section}, ресурсная позиция {index + 1}",
                "unit": "шт.",
                "quantity": "1",
                "unitPrice": "100.00",
                "quantityBasis": (
                    "Тестовый проектный объём; подтвердить ведомостью."
                ),
                "priceBasis": (
                    "Предварительная QA-цена; проверить источник."
                ),
            }
            for index in range(self.rows_per_section)
        ]
        payload = _technology_section_fixture(section, rows)
        self.sections_by_hash[section_hash] = payload
        return json.dumps(payload, ensure_ascii=False)


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


def _full_estimate_run_payload() -> dict[str, object]:
    return {
        "threadId": "thread_full_estimate_product_qa_01",
        "runId": "run_full_estimate_product_qa_01",
        "state": None,
        "messages": [
            {
                "id": "message_full_estimate_product_qa_01",
                "role": "user",
                "content": (
                    "Составь полную подробную ресурсную смету строительства "
                    "девятиэтажного монолитного жилого дома на 72 квартиры "
                    "общей площадью 6200 м² в Казани, от подготовки площадки "
                    "до ввода в эксплуатацию. Работы, материалы, оборудование "
                    "и услуги укажи отдельными строками. Не ограничивай "
                    "количество позиций; неизвестные данные пометь допущениями."
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


def _load_all_estimate_rows(
    client: TestClient,
    *,
    project_id: str,
    headers: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    offset = 0
    total_rows: int | None = None
    version: int | None = None
    first_page: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    row_ids: set[str] = set()
    while True:
        response = client.get(
            f"/v1/projects/{project_id}/estimate?offset={offset}&limit=100",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        page = response.json()
        first_page = first_page or page
        row_page = page["rowPage"]
        assert row_page["offset"] == offset
        assert row_page["limit"] == 100
        total_rows = row_page["totalRows"] if total_rows is None else total_rows
        version = page["version"] if version is None else version
        assert row_page["totalRows"] == total_rows
        assert page["version"] == version
        for row in page["rows"]:
            assert row["id"] not in row_ids
            row_ids.add(row["id"])
            rows.append(row)
        if not row_page["hasMore"]:
            break
        assert page["rows"]
        offset += len(page["rows"])
    assert first_page is not None
    assert len(rows) == total_rows
    return first_page, rows


def _wait_for_estimate_page(
    client: TestClient,
    *,
    project_id: str,
    headers: dict[str, str],
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_page: dict[str, Any] | None = None
    while True:
        response = client.get(
            f"/v1/projects/{project_id}/estimate",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        page = response.json()
        last_page = page
        if page["rowPage"]["totalRows"] > 0:
            return page
        if time.monotonic() >= deadline:
            raise AssertionError(
                "estimate rows were not materialized before timeout: "
                f"{last_page}"
            )
        time.sleep(0.5)


def test_public_agui_materializes_tenant_scoped_estimate_without_db_seeding(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    database_path = tmp_path / "public-estimate-journey.db"
    settings = _settings(database_path)
    transport = _GeneralEstimateTransport()
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
        tool_starts = [
            event
            for event in events
            if event["type"] == "TOOL_CALL_START"
        ]
        # The AG-UI chat stream frees the composer after the compact estimate
        # acknowledgement. The durable estimate pipeline continues on its own
        # resumable stream and must not be re-synthesized here.
        assert [event["toolCallName"] for event in tool_starts] == ["present"]
        present_tool_call_id = tool_starts[0]["toolCallId"]
        present_args_event = next(
            event
            for event in events
            if event["type"] == "TOOL_CALL_ARGS"
            and event["toolCallId"] == present_tool_call_id
        )
        present_args = json.loads(present_args_event["delta"])
        assert present_args["$type"] == "EstimateGenerationActivity"
        assert present_args["activitySchemaVersion"] == "1.0"
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
        assert present_args["activityProjectId"] == project_id
        assert present_args["generationRunId"].startswith("run_estimate_generation_")
        assert present_args["projectCaseVersion"] == 1

        estimate_value = _wait_for_estimate_page(
            client,
            project_id=project_id,
            headers=_bearer(customer),
        )
        assert estimate_value["projectId"] == project_id
        assert estimate_value["version"] == 1
        assert estimate_value["status"] in {"draft", "needs_input"}
        assert estimate_value["estimateTitle"].startswith(
            "Механизированная штукатурка"
        )
        assert len(estimate_value["rows"]) >= 3
        assert {"work", "material", "service"} <= {
            row["kind"] for row in estimate_value["rows"]
        }
        assert estimate_value["pricing"]["status"] == "unpriced"
        assert estimate_value["totals"]["total"] != "0.00"
        generation = estimate_value["generation"]
        assert generation["estimateGenerationRunId"].startswith(
            "run_estimate_generation_"
        )
        assert generation["technologyCardRevisionId"].startswith(
            "technology_card_revision_"
        )
        assert generation["technologyCardHash"].startswith("sha256:")
        assert generation["qualityStatus"] == "pending"
        assert all(row["operationId"] for row in estimate_value["rows"])
        assert all(row["resourceId"] for row in estimate_value["rows"])
        assert all(
            row["technologyCardVersion"]
            == generation["technologyCardRevisionId"]
            for row in estimate_value["rows"]
        )
        assert sum(bool(row.get("evidenceId")) for row in estimate_value["rows"]) == 3

        generation_status = client.get(
            f"/v1/projects/{project_id}/estimate/generation",
            headers=_bearer(customer),
        )
        assert generation_status.status_code == 200, generation_status.text
        durable_run = generation_status.json()["generationRun"]
        assert durable_run["id"] == generation["estimateGenerationRunId"]
        assert durable_run["status"] == "needs_input"
        assert durable_run["stage"] == "reconciliation"
        assert durable_run["qualityStatus"] == "failed"
        assert durable_run["result"] == {
            "documentId": estimate_value["documentId"],
            "estimateVersion": estimate_value["version"],
        }

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
                "originType": "ai_proposal",
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
        assert tool_message["args"]["version"] == 1
        assert tool_message["args"]["rows"] == []
        assert tool_message["args"]["rowPage"]["limit"] == 0

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


def test_fixture_transport_preserves_every_large_estimate_row(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    database_path = tmp_path / "full-estimate-product-qa.db"
    settings = _settings(database_path)
    transport = _FullEstimateTransport()
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

    with TestClient(create_app(settings)) as client:
        _register_owner(client, settings)
        _connect_codex_through_authority(client, settings)
        customer = _mobile_register(
            client,
            email="full-estimate-product-qa@example.com",
            device_name="Full estimate QA client",
        )
        _grant_estimate_access(client, user_id=customer["user"]["id"])

        run = client.post(
            "/v1/chat/ag-ui",
            headers={
                **_bearer(customer),
                "Accept": "text/event-stream",
            },
            json=_full_estimate_run_payload(),
        )
        assert run.status_code == 200, run.text
        events = _sse_events(run.text)
        assert events[-1]["type"] == "RUN_FINISHED"
        assert events[-1]["outcome"] == {"type": "success"}
        # The public chat stream must remain compact; the separate durable
        # estimate stream replays the real A2A role activity from the journal.
        assert sum(
            event.get("toolCallName") == "estimate_technology_role"
            for event in events
        ) == 0
        assert sum(
            event.get("toolCallName") == "estimate_price_research"
            for event in events
        ) == 0
        assert sum(
            event.get("toolCallName") == "estimate_independent_review"
            for event in events
        ) == 0

        present_calls = [
            event
            for event in events
            if event.get("type") == "TOOL_CALL_START"
            and event.get("toolCallName") == "present"
        ]
        assert len(present_calls) == 1
        present_call = present_calls[0]

        present_delta = "".join(
            str(event.get("delta") or "")
            for event in events
            if event.get("type") == "TOOL_CALL_ARGS"
            and event.get("toolCallId") == present_call["toolCallId"]
        )
        present_args = json.loads(present_delta)
        assert present_args["$type"] == "EstimateGenerationActivity"
        assert present_args["activitySchemaVersion"] == "1.0"
        assert present_args["projectCaseVersion"] == 1
        assert isinstance(present_args["activityProjectId"], str)
        assert present_args["generationRunId"].startswith(
            "run_estimate_generation_"
        )
        expected_rows = transport.section_count * transport.rows_per_section

        threads = client.get(
            "/v1/chat/threads",
            headers=_bearer(customer),
        )
        assert threads.status_code == 200, threads.text
        [thread] = threads.json()["threads"]
        project_id = thread["projectId"]

        _wait_for_estimate_page(
            client,
            project_id=project_id,
            headers=_bearer(customer),
        )
        estimate_value, estimate_rows = _load_all_estimate_rows(
            client,
            project_id=project_id,
            headers=_bearer(customer),
        )
        assert len(estimate_rows) == expected_rows
        assert estimate_value["pricing"]["totalRows"] == expected_rows
        assert estimate_value["totals"]["total"] == "120000.00"
        assert {row["kind"] for row in estimate_rows} == {
            "work",
            "material",
            "equipment",
            "service",
        }
        generation = estimate_value["generation"]
        assert generation["estimateGenerationRunId"].startswith(
            "run_estimate_generation_"
        )
        assert generation["technologyCardRevisionId"].startswith(
            "technology_card_revision_"
        )
        assert generation["technologyCardHash"].startswith("sha256:")
        assert generation["qualityStatus"] == "passed"
        assert all(row["operationId"] for row in estimate_rows)
        assert all(row["resourceId"] for row in estimate_rows)
        assert all(row["evidenceId"] for row in estimate_rows)
        assert all(row["lineConfidence"] == "preliminary" for row in estimate_rows)
        assert all(
            row["technologyCardVersion"]
            == generation["technologyCardRevisionId"]
            for row in estimate_rows
        )
        generation_status = client.get(
            f"/v1/projects/{project_id}/estimate/generation",
            headers=_bearer(customer),
        )
        assert generation_status.status_code == 200, generation_status.text
        durable_run = generation_status.json()["generationRun"]
        assert durable_run["id"] == generation["estimateGenerationRunId"]
        assert durable_run["status"] == "ready"
        assert durable_run["stage"] == "complete"
        assert durable_run["qualityStatus"] == "passed"
        assert durable_run["result"] == {
            "documentId": estimate_value["documentId"],
            "estimateVersion": estimate_value["version"],
        }

        documents = client.get(
            "/v1/documents",
            headers=_bearer(customer),
        )
        assert documents.status_code == 200, documents.text
        [document] = documents.json()["documents"]
        assert document["rowCount"] == expected_rows

        exported = client.get(
            f"/v1/projects/{project_id}/estimate/export/csv",
            headers=_bearer(customer),
        )
        assert exported.status_code == 200, exported.text
        csv_text = exported.content.decode("utf-8-sig")
        assert csv_text.count("ресурсная позиция") == expected_rows
        assert transport.calls[0]["execution_profile"] == "estimate-plan"
        assert len(transport.calls) == 1 + (transport.section_count * 7)
        assert sum(
            str(call["execution_profile"]).startswith("estimate-role:")
            for call in transport.calls
        ) == transport.section_count * 5
        assert sum(
            str(call["execution_profile"]).startswith("estimate-pricing:")
            for call in transport.calls
        ) == transport.section_count
        assert sum(
            str(call["execution_profile"]).startswith("estimate-review:")
            for call in transport.calls
        ) == transport.section_count
