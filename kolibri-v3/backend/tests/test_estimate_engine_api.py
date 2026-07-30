from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.database import connect_database, migration_paths
from app.estimate_engine import canonical_json, content_hash
from app.estimate_intake import PLASTERING_INTAKE_SCHEMA, PlasteringIntake
from app.estimate_reconciliation import reconcile_ai_candidate_estimates
from app.main import create_app
from app.product_widgets import materialize_engine_estimate_widget
from fastapi.testclient import TestClient

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct-horse-battery-staple"
REGION = "Республика Татарстан"
PRICE_FIXTURE: dict[str, tuple[str, str]] = {
    "survey": ("m2", "35.00"),
    "surface_cleaning": ("m2", "90.00"),
    "protection": ("m2", "48.00"),
    "primer_application": ("m2", "75.00"),
    "primer_material": ("l", "120.00"),
    "beacon_installation": ("m2", "160.00"),
    "beacon_profile": ("ea", "85.00"),
    "corner_installation": ("m", "95.00"),
    "corner_profile": ("ea", "95.00"),
    "mesh_installation": ("m2", "220.00"),
    "reinforcing_mesh": ("m2", "75.00"),
    "plaster_application": ("m2", "520.00"),
    "plaster_mix": ("bag", "470.00"),
    "water": ("m3", "180.00"),
    "electricity": ("kWh", "8.50"),
    "plaster_machine": ("shift", "8500.00"),
    "delivery": ("trip", "3500.00"),
    "lifting": ("t", "1800.00"),
    "slopes": ("m2", "1450.00"),
    "smoothing": ("m2", "140.00"),
    "quality_control": ("m2", "65.00"),
    "cleanup": ("m2", "65.00"),
    "waste_removal": ("trip", "6500.00"),
    "consumables": ("set", "8500.00"),
}
LATEST_SCHEMA_VERSION = int(migration_paths()[-1].name.split("_", 1)[0])


def test_intake_contract_accepts_complete_technology_assumption() -> None:
    technology_assumption = (
        "Estimate Engine должен сохранить обязательные технологические этапы: "
        "обследование, очистку, защиту, грунт, маяки, углы и сетку по условиям, "
        "смесь, нанесение, воду, электричество, штукатурную станцию, доставку, "
        "подъём, откосы по условиям, финишное сглаживание, контроль качества, "
        "уборку, вывоз и расходники."
    )
    assert 300 < len(technology_assumption) <= 600
    payload = {
        "title": "Смета штукатурки 358 м²",
        "region": REGION,
        **{
            "wallAreaM2": "358",
            "averageThicknessMm": "15",
            "material": "gypsum",
            "applicationMethod": "mechanized",
            "wastePercent": "10",
            "protectionAreaM2": "358",
            "wallHeightM": "3",
            "beaconSpacingM": "1.5",
            "cornerLengthM": "0",
            "meshAreaPercent": "10",
            "slopesAreaM2": "0",
            "plasterBagWeightKg": "30",
            "primerPasses": 1,
            "wasteRemovalTrips": "1",
        },
        "assumptions": [technology_assumption],
        "candidatePrices": [],
    }

    intake = PlasteringIntake.model_validate(payload)

    assert intake.assumptions == [technology_assumption]
    assert (
        PLASTERING_INTAKE_SCHEMA["properties"]["assumptions"]["items"][
            "maxLength"
        ]
        == 600
    )


def _register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/v1/auth/register",
        headers=ORIGIN,
        json={
            "email": email,
            "name": email.split("@", 1)[0],
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.json()["user"]


def _grant_estimate_access(
    database_path: Path,
    *,
    tenant_id: str,
    user_id: str,
) -> None:
    database = sqlite3.connect(database_path)
    try:
        database.execute("PRAGMA foreign_keys = ON")
        database.execute(
            """
            INSERT INTO product_entitlement_grants (
                tenant_id, user_id, entitlement_code, status,
                grant_epoch, source, created_at, updated_at
            ) VALUES (
                ?, ?, 'construction.estimates.use', 'active',
                1, 'subscription_policy', unixepoch(), unixepoch()
            )
            """,
            (tenant_id, user_id),
        )
        database.commit()
    finally:
        database.close()


def _seed_project(
    database_path: Path,
    *,
    tenant_id: str,
    user_id: str,
) -> str:
    _grant_estimate_access(
        database_path,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    project_id = "project_engine_api_01"
    thread_id = "thread_engine_api_01"
    now = "2026-07-29T00:00:00Z"
    database = sqlite3.connect(database_path)
    try:
        database.execute("PRAGMA foreign_keys = ON")
        database.execute(
            """
            INSERT INTO projects (
                tenant_id, id, created_by_user_id, title, status,
                primary_thread_id, created_at, updated_at
            ) VALUES (?, ?, ?, 'Штукатурка 358 м²', 'active', ?, ?, ?)
            """,
            (tenant_id, project_id, user_id, thread_id, now, now),
        )
        database.execute(
            """
            INSERT INTO construction_objects (
                tenant_id, id, project_id, name, name_source,
                created_at, updated_at
            ) VALUES (?, 'object_engine_api_01', ?,
                      'Жилой дом, Альметьевск', 'user', ?, ?)
            """,
            (tenant_id, project_id, now, now),
        )
        database.execute(
            """
            INSERT INTO chat_threads (
                tenant_id, id, project_id, kind, title, status,
                message_count, run_count, created_at, updated_at
            ) VALUES (?, ?, ?, 'primary', 'Штукатурка 358 м²', 'regular',
                      0, 0, ?, ?)
            """,
            (tenant_id, thread_id, project_id, now, now),
        )
        database.execute(
            """
            INSERT INTO document_slots (
                tenant_id, id, project_id, slot_type, version, status,
                content_json, created_at, updated_at
            ) VALUES (?, 'document_engine_api_01', ?, 'estimate', 1,
                      'empty', NULL, ?, ?)
            """,
            (tenant_id, project_id, now, now),
        )
        database.execute(
            """
            INSERT INTO chat_messages (
                tenant_id, id, project_id, thread_id, sequence,
                client_message_id, role, content_text,
                created_by_user_id, created_at
            ) VALUES (?, 'message_engine_api_01', ?, ?, 1,
                      'client_engine_api_01', 'user',
                      '358 м² механизированной штукатурки, слой 15 мм, Татарстан',
                      ?, ?)
            """,
            (tenant_id, project_id, thread_id, user_id, now),
        )
        database.execute(
            """
            INSERT INTO chat_runs (
                tenant_id, id, project_id, thread_id, client_run_id,
                request_hash, input_message_id, requested_by_user_id,
                selected_profile, status, last_event_sequence,
                heartbeat_at, created_at, updated_at
            ) VALUES (?, 'run_engine_api_01', ?, ?,
                      'client_run_engine_api_01', ?,
                      'message_engine_api_01', ?, 'codex-cli',
                      'running', 0, ?, ?, ?)
            """,
            (
                tenant_id,
                project_id,
                thread_id,
                "sha256:" + ("a" * 64),
                user_id,
                now,
                now,
                now,
            ),
        )
        database.commit()
    finally:
        database.close()
    return project_id


def _payload(
    *,
    expected_version: int = 1,
    prices: bool = True,
) -> dict[str, object]:
    source = {
        "sourceId": "source_tatarstan_fixture",
        "sourceType": "supplier_offer",
        "label": "Проверенное предложение поставщика",
        "reference": "offer-2026-07-29",
        "url": "https://supplier.example/offers/2026-07-29",
        "region": REGION,
        "observedAt": "2026-07-29T00:00:00+00:00",
        "validUntil": "2026-08-29",
        "verified": True,
    }
    return {
        "expectedEstimateVersion": expected_version,
        "region": REGION,
        "title": "Смета механизированной штукатурки 358 м²",
        "scope": {
            "wallAreaM2": "358",
            "averageThicknessMm": "15",
            "material": "gypsum",
            "applicationMethod": "mechanized",
            "wastePercent": "10",
            "protectionAreaM2": "80",
            "wallHeightM": "3",
            "beaconSpacingM": "1.5",
            "cornerLengthM": "60",
            "meshAreaPercent": "10",
            "slopesAreaM2": "24",
            "plasterBagWeightKg": "30",
            "primerPasses": 1,
            "wasteRemovalTrips": "1",
        },
        "prices": (
            [
                {
                    "itemCode": code,
                    "unit": unit,
                    "unitPrice": price,
                    "currency": "RUB",
                    "vatMode": "included",
                    "confidence": "0.95",
                    "source": source,
                }
                for code, (unit, price) in sorted(PRICE_FIXTURE.items())
            ]
            if prices
            else []
        ),
        "terms": {
            "overheadPercent": "10",
            "profitPercent": "15",
            "discountPercent": "5",
            "taxPercent": "20",
        },
        "requireReleaseReady": prices,
    }


def _headers(client: TestClient, key: str) -> dict[str, str]:
    csrf = client.cookies.get("kolibri_v3_csrf")
    assert csrf
    return {
        **ORIGIN,
        "X-CSRF-Token": csrf,
        "Idempotency-Key": key,
    }


def test_engine_api_persists_project_case_technology_card_and_estimate_once(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "estimate-engine-api.db"
    settings = Settings.for_testing(database_url=database_path)
    with TestClient(create_app(settings)) as client:
        user = _register(client, "engine@example.com")
        project_id = _seed_project(
            database_path,
            tenant_id=user["tenantId"],
            user_id=user["id"],
        )
        url = f"/v1/projects/{project_id}/estimate/calculations/plastering"
        headers = _headers(client, "estimate-engine-api-key-0001")
        created = client.post(url, headers=headers, json=_payload())
        assert created.status_code == 201
        value = created.json()
        assert value["replayed"] is False
        assert value["projectCaseVersion"] == 1
        assert value["estimateVersion"] == 1
        assert value["result"]["validation"]["status"] == "passed"
        assert value["result"]["items"]
        assert value["estimate"]["totals"]["total"] == "618190.05"
        assert value["estimate"]["pricing"]["status"] == "sourced"
        assert value["estimate"]["rows"][0]["id"].startswith("row_")

        replayed = client.post(url, headers=headers, json=_payload())
        assert replayed.status_code == 201
        assert replayed.json()["replayed"] is True
        assert replayed.json()["calculationId"] == value["calculationId"]
        assert replayed.json()["result"]["resultHash"] == (
            value["result"]["resultHash"]
        )

        changed_payload = _payload()
        changed_payload["title"] = "Другой вход"
        conflict = client.post(url, headers=headers, json=changed_payload)
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "idempotency_conflict"

        versions = client.get(f"/v1/projects/{project_id}/estimate/versions")
        assert versions.status_code == 200
        assert versions.json()["versions"][0]["originType"] == (
            "engine_calculation"
        )

    database = sqlite3.connect(database_path)
    try:
        assert (
            database.execute("PRAGMA user_version").fetchone()[0]
            == LATEST_SCHEMA_VERSION
        )
        assert database.execute(
            "SELECT COUNT(*) FROM project_cases"
        ).fetchone()[0] == 1
        assert database.execute(
            "SELECT COUNT(*) FROM technology_cards"
        ).fetchone()[0] == 1
        assert database.execute(
            "SELECT COUNT(*) FROM estimate_calculations"
        ).fetchone()[0] == 1
        assert database.execute(
            "SELECT COUNT(*) FROM estimate_versions"
        ).fetchone()[0] == 1
        assert database.execute(
            "SELECT COUNT(*) FROM audit_events"
        ).fetchone()[0] == 1
    finally:
        database.close()


def test_engine_api_enforces_tenant_version_and_release_price_gates(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "estimate-engine-security.db"
    settings = Settings.for_testing(database_url=database_path)
    with TestClient(create_app(settings)) as client:
        first = _register(client, "first@example.com")
        project_id = _seed_project(
            database_path,
            tenant_id=first["tenantId"],
            user_id=first["id"],
        )
        url = f"/v1/projects/{project_id}/estimate/calculations/plastering"

        release_without_prices = _payload(prices=False)
        release_without_prices["requireReleaseReady"] = True
        rejected = client.post(
            url,
            headers=_headers(client, "estimate-engine-api-key-0002"),
            json=release_without_prices,
        )
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "estimate_calculation_invalid"

        first_created = client.post(
            url,
            headers=_headers(client, "estimate-engine-api-key-0003"),
            json=_payload(),
        )
        assert first_created.status_code == 201
        second_created = client.post(
            url,
            headers=_headers(client, "estimate-engine-api-key-0004"),
            json=_payload(expected_version=1),
        )
        assert second_created.status_code == 201
        assert second_created.json()["estimateVersion"] == 2

        stale = client.post(
            url,
            headers=_headers(client, "estimate-engine-api-key-0005"),
            json=_payload(expected_version=1),
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "estimate_version_conflict"

        second = _register(client, "second@example.com")
        assert second["tenantId"] != first["tenantId"]
        _grant_estimate_access(
            database_path,
            tenant_id=second["tenantId"],
            user_id=second["id"],
        )
        hidden = client.get(f"/v1/projects/{project_id}/estimate")
        assert hidden.status_code == 404
        assert hidden.json()["code"] == "estimate_not_found"

    database = sqlite3.connect(database_path)
    try:
        # The rejected release and stale write are atomic and leave no residue.
        assert database.execute(
            "SELECT COUNT(*) FROM project_cases"
        ).fetchone()[0] == 2
        assert database.execute(
            "SELECT COUNT(*) FROM estimate_calculations"
        ).fetchone()[0] == 2
        assert database.execute(
            "PRAGMA foreign_key_check"
        ).fetchall() == []
    finally:
        database.close()


def test_chat_intake_materializes_engine_rows_not_model_rows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "estimate-engine-chat.db"
    settings = Settings.for_testing(database_url=database_path)
    with TestClient(create_app(settings)) as client:
        user = _register(client, "chat-engine@example.com")
        project_id = _seed_project(
            database_path,
            tenant_id=user["tenantId"],
            user_id=user["id"],
        )
        intake = PlasteringIntake.model_validate(
            {
                "title": "Смета штукатурки 358 м²",
                "region": REGION,
                **_payload()["scope"],
                "assumptions": [
                    "Высота стен предварительно принята 3 м.",
                    "Локальное армирование принято на 10% площади.",
                ],
                "candidatePrices": [
                    {
                        "itemCode": code,
                        "unitPrice": (
                            "15000.00"
                            if code == "survey"
                            else (
                                "8000.00"
                                if code == "quality_control"
                                else "1.00"
                            )
                        ),
                    }
                    for code in sorted(PRICE_FIXTURE)
                ],
            }
        )
        widget = materialize_engine_estimate_widget(
            settings,
            SimpleNamespace(
                tenant_id=user["tenantId"],
                project_id=project_id,
                run_id="run_engine_api_01",
                public_run_id="run_public_engine_api_01",
            ),
            intake=intake,
            provider_profile="codex-cli",
        )
        assert widget.arguments["$type"] == "EstimateEditor"
        assert widget.arguments["generation"]["providerProfile"] == (
            "estimate-engine"
        )
        assert widget.arguments["totals"]["total"] == "618190.05"
        assert len(widget.arguments["rows"]) == 24
        assert all(
            row["enginePriceProvenance"]["verified"] is False
            for row in widget.arguments["rows"]
        )
        assert all(
            row["enginePriceProvenance"]["sourceUrl"]
            == (
                "document://regional-price-snapshot/"
                "plastering-reference-2026-07-29-1"
            )
            for row in widget.arguments["rows"]
        )
        assert all(
            "url" not in row["enginePriceProvenance"]
            for row in widget.arguments["rows"]
        )
        assert "независимой проверки" in widget.fallback_text
        assert widget.tool_result is not None
        assert widget.tool_result["candidatePriceCount"] == 24
        assert widget.tool_result["candidateOutlierCount"] == 24
        assert widget.tool_result["priceSnapshotVersion"] == (
            "plastering-reference/2026-07-29.1"
        )

    database = sqlite3.connect(database_path)
    try:
        origin = database.execute(
            "SELECT origin_type FROM estimate_versions"
        ).fetchone()[0]
        assert origin == "engine_calculation"
        result = database.execute(
            "SELECT result_json FROM estimate_calculations"
        ).fetchone()[0]
        assert '"engineVersion":"kolibri-estimate-engine/1.0.0"' in result
        assert '"status":"blocked"' in result
    finally:
        database.close()


def test_reconciliation_appends_one_idempotent_server_priced_version(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "estimate-reconciliation.db"
    settings = Settings.for_testing(database_url=database_path)
    with TestClient(create_app(settings)) as client:
        user = _register(client, "estimate-repair@example.com")
        project_id = _seed_project(
            database_path,
            tenant_id=user["tenantId"],
            user_id=user["id"],
        )
        intake = PlasteringIntake.model_validate(
            {
                "title": "Смета штукатурки 358 м²",
                "region": REGION,
                **_payload()["scope"],
                "assumptions": ["Тест восстановления ценовой власти."],
                "candidatePrices": [
                    {
                        "itemCode": code,
                        "unitPrice": (
                            "15000.00"
                            if code == "survey"
                            else (
                                "8000.00"
                                if code == "quality_control"
                                else "1.00"
                            )
                        ),
                    }
                    for code in sorted(PRICE_FIXTURE)
                ],
            }
        )
        widget = materialize_engine_estimate_widget(
            settings,
            SimpleNamespace(
                tenant_id=user["tenantId"],
                project_id=project_id,
                run_id="run_engine_api_01",
                public_run_id="run_public_engine_api_01",
            ),
            intake=intake,
            provider_profile="mimo-code",
        )
        expected_total = widget.arguments["totals"]["total"]

    database = connect_database(database_path)
    try:
        slot = database.execute(
            """
            SELECT tenant_id, id, version, content_json
            FROM document_slots
            WHERE project_id = ? AND slot_type = 'estimate'
            """,
            (project_id,),
        ).fetchone()
        assert slot is not None
        contaminated = json.loads(str(slot["content_json"]))
        for row in contaminated["rows"]:
            row["engine_price_provenance"]["sourceType"] = "ai_candidate"
            row["engine_price_provenance"]["verified"] = False
        contaminated_json = canonical_json(contaminated)
        database.execute(
            """
            UPDATE document_slots
            SET content_json = ?
            WHERE tenant_id = ? AND id = ? AND version = ?
            """,
            (
                contaminated_json,
                slot["tenant_id"],
                slot["id"],
                slot["version"],
            ),
        )
        database.execute(
            """
            UPDATE estimate_versions
            SET content_json = ?, content_hash = ?
            WHERE tenant_id = ? AND document_id = ? AND version = ?
            """,
            (
                contaminated_json,
                content_hash(contaminated),
                slot["tenant_id"],
                slot["id"],
                slot["version"],
            ),
        )

        first = reconcile_ai_candidate_estimates(database, apply=True)
        assert len(first) == 1
        assert first[0].status == "repaired"
        assert first[0].previous_version == 1
        assert first[0].replacement_version == 2
        assert first[0].replacement_total == expected_total
        assert reconcile_ai_candidate_estimates(database, apply=True) == []

        current = database.execute(
            """
            SELECT version, content_json
            FROM document_slots
            WHERE tenant_id = ? AND id = ?
            """,
            (slot["tenant_id"], slot["id"]),
        ).fetchone()
        assert current is not None
        assert int(current["version"]) == 2
        assert "ai_candidate" not in str(current["content_json"])
        assert database.execute(
            """
            SELECT status
            FROM estimate_versions
            WHERE tenant_id = ? AND document_id = ? AND version = 1
            """,
            (slot["tenant_id"], slot["id"]),
        ).fetchone()[0] == "stale"
        assert database.execute(
            """
            SELECT COUNT(*)
            FROM audit_events
            WHERE tenant_id = ?
              AND action = 'estimate.price_authority_reconciled'
            """,
            (slot["tenant_id"],),
        ).fetchone()[0] == 1
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        database.close()
